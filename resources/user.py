from flask_restful import Resource
from flask import request, make_response, render_template
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_refresh_token_required,
    get_jwt_identity,
    jwt_required,
    fresh_jwt_required,
    get_raw_jwt,
)
from models.image import ImageModel
from models.user import UserModel
from schemas.user import UserSchema
from schemas.image import ImageSchema
from argon2 import PasswordHasher, exceptions
from blacklist import BLACKLIST
import datetime
import json


user_schema = UserSchema()
ph = PasswordHasher()


class UserUpdate(Resource):
    @classmethod
    @fresh_jwt_required
    def put(cls):
        identity = get_jwt_identity()
        authed_user = UserModel.find_by_id(identity)

        user_json = request.get_json()
        if "username" in user_json:
            authed_user.username = user_json["username"]
            authed_user.save_to_db()
        if "email" in user_json:
            authed_user.email = user_json["email"]
            authed_user.save_to_db()
        if "password" in user_json:
            authed_user.password = ph.hash(user_json["password"])
            authed_user.save_to_db()
        if authed_user.email and authed_user.password:
            authed_user.github_activated = True
            authed_user.save_to_db()

        #     authed_user.github_activated = True
        #     authed_user.save_to_db()
        return (
            {
                "message": "successful update",
                "github_verified": authed_user.github_activated,
            },
            201,
        )


class UserInfo(Resource):
    @classmethod
    @jwt_required
    def get(cls):
        identity = get_jwt_identity()
        user = UserModel.find_by_id(identity)
        if user:
            return (
                {
                    "user_id": user.id,
                    "is_verified": user.activated,
                    "github_verified": user.github_activated,
                },
                200,
            )
        return {"message": "user not found"}, 404


class User(Resource):
    @classmethod
    @fresh_jwt_required
    def delete(cls, username: str):
        user = UserModel.find_by_username(username)
        identity = get_jwt_identity()
        user_confirm = UserModel.find_by_id(identity)
        if user.username == user_confirm.username:
            user.delete_from_db()
            return {"msg": "user deleted"}, 201
        return {"msg": "unable to find user or you are not the owner of that acc"}, 404

    @classmethod
    def get(cls, username: str):
        user = UserModel.find_by_username(username)
        if user:
            return (
                {"user": user.id, "images": [img.json() for img in user.images.all()]},
                200,
            )
        else:
            return {"message": "cannot find user"}


class UserRegister(Resource):
    @classmethod
    def post(cls):
        user_json = request.get_json()
        password = ph.hash(user_json["password"])
        user_json["password"] = password
        user = user_schema.load(user_json)

        if UserModel.find_by_username(user.username):
            return {"message": "username exists"}, 400

        user.save_to_db()
        user.send_confirmation_email()
        return {"message": "you are now registered"}, 201


class UserLogin(Resource):
    @classmethod
    def post(cls):
        user_json = request.get_json()
        user_data = user_schema.load(user_json, partial=("email",))

        user = UserModel.find_by_username(user_data.username)

        try:
            if user and ph.verify(user.password, user_data.password):
                delta = datetime.timedelta(hours=1)
                access_token = create_access_token(
                    identity=user.id, fresh=True, expires_delta=delta
                )
                refresh_token = create_refresh_token(user.id)
                return (
                    {"access_token": access_token, "refresh_token": refresh_token , "username": user.username},
                    200,
                )
            else:
                return {"message": "incorrect login"}, 401
        except exceptions.VerifyMismatchError:
            return {"message": "invalid credentials"}, 401


class UserLogout(Resource):
    @classmethod
    @jwt_required
    def get(cls):
        jti = get_raw_jwt()["jti"]
        print(jti)
        BLACKLIST.add(jti)
        return {"message": "Successfully logged out"}, 200


class UserVerify(Resource):
    @classmethod
    def get(cls, user_id):
        user = UserModel.find_by_id(user_id)
        if not user:
            return {"message": "No user with id"}, 404
        if user.activated:
            return {"message": "user is already activated"}, 400

        user.activated = True
        user.save_to_db()
        headers = {"Content-Type": "text/html"}
        return make_response(
            render_template("email_confirm.html", email=user.email), 200, headers
        )

    @classmethod
    def post(cls, user_id):
        user = UserModel.find_by_id(user_id)
        if not user:
            return {"error": "User does not exist"}, 404

        if user.activated:
            return {"message": "user is already activated"}, 400
        try:

            user.send_confirmation_email()
            return {"message": "confirmation resend successful"}, 201

        except:
            return {"message": "confirmation resend fail"}, 500


class TokenRefresh(Resource):
    @classmethod
    @jwt_refresh_token_required
    def post(cls):
        current_user = get_jwt_identity()
        new_token = create_access_token(
            identity=current_user, fresh=False, expires_delta=False
        )
        return {"access_token": new_token}, 200
