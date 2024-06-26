from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
from models import user
import hashlib, re, uuid
from datetime import datetime, timedelta, timezone
from postmarker.core import PostmarkClient

app = Flask(__name__)

# Set secret key
app.secret_key = "thisIsATest"
salt = os.environ.get("SALT")
is_verified = False
postmark = PostmarkClient(server_token=os.environ.get("POSTMARK_TOKEN"))
email_pattern = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

img = os.path.join("static", "images")
file = os.path.join(img, "img.jpg")


@app.route("/")
def index():
    if "username" not in session:
        return redirect(url_for("signup"))
    return render_template(
        "index.html", img=file,
    )


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        invalid_fields = []
        username = request.form["username"]
        name = request.form["name"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        email = request.form["email"]
        token = uuid.uuid4()
        user_account = user.getByUsername(username)

        if len(username) < 4 or len(username) >= 12:
            invalid_fields.append(
                {
                    "id": "username",
                    "message": "Username must contain characters between 4 and 12",
                }
            )
        if not username.isalnum():
            invalid_fields.append(
                {
                    "id": "username",
                    "message": "Username may only contain letters and numbers",
                }
            )
        if email_pattern == email:
            invalid_fields.append({"id": "email", "message": "Email is invalid"})
        if user_account is not None:
            invalid_fields.append(
                {"id": "username", "message": "Username already exist"}
            )
        if len(password) < 4:
            invalid_fields.append(
                {
                    "id": "password",
                    "message": "Password length should be not be less than four characters",
                }
            )
        if password != confirm_password:
            invalid_fields.append(
                {"id": "confirm_password", "message": "Passwords must match!"}
            )

        hashed_string = hashlib.sha256()
        hashed_string.update((salt + password).encode("utf-8"))
        hashed_pass = hashed_string.hexdigest()

        if len(invalid_fields) == 0:
            user_id = user.createUser(name, username, email, hashed_pass, is_verified)
            user.createEmailUUID(token, user_id)
            confirm_url = url_for("emailConfirmation", token=token, _external=True)
            html = render_template("confirmation.html", confirm_url=confirm_url)

            postmark.emails.send(
                From="email-signature",
                To=email,
                Subject="Please confirm your email",
                HtmlBody=html,
            )
            return {
                "status": "success",
                "message": "Your account has been successfully created. A link has been emailed to you for account confirmation.",
            }
        return {
            "status": "fail",
            "invalid_fields": invalid_fields,
        }
    if request.method == "GET":
        return render_template("signup.html")


@app.route("/resend-verification-link", methods=["GET", "POST"])
def resetVerificationLink():
    if request.method == "POST":
        invalid_fields = []
        email = request.form["email"]
        user_info = user.getByEmail(email)

        if user_info is None:
            print("no user found")
            invalid_fields.append(
                {
                    "id": "email",
                    "message": "The email is not on file, click register to signup",
                }
            )
        elif user_info and user_info[1] == "false":
            new_token = str(uuid.uuid4())
            user.updateEmailUUID(user_info[0], new_token)
            # confirm_url = url_for("emailConfirmation", new_token=new_token, _external=True)
            # html = render_template("confirmation.html", confirm_url=confirm_url)

            # postmark.emails.send(
            #     From="email-signature",
            #     To=email,
            #     Subject="Please confirm your email",
            #     HtmlBody=html,
            # )
            invalid_fields.append(
                {
                    "id": "email",
                    "message": "A new email verification has been sent"
                }
            )
        else:
            invalid_fields.append(
                {
                    "id": "email",
                    "message": "Your email is already verified"
                }
            )
    return render_template("reset_email_verification.html")


@app.route("/confirmation/<token>", methods=["GET"])
def emailConfirmation(token):
    user_verification = user.confirmVerificationCode(token)
    is_verified = user_verification[1]
    email_uuid_match = user_verification[2] == token
    time_stamp = user_verification[-1]

    if user_verification is None:
        flash("Invalid verification link.", "error")
        print("Invalid verification link.")

    if datetime.now(timezone.utc) - time_stamp > timedelta(hours=24):
        flash("Your verification link has expired", "error")
        print("Your verification link has expired")
        return render_template("linkexpired.html")

    if is_verified == "false" and email_uuid_match:
        user.isVerified(user_verification[0], True)
        flash("Verification complete", "success")
        return redirect(url_for("login"))
    return render_template("confirmation.html")


@app.route("/password-reset", methods=["GET", "POST"])
def resetPassword():
    if request.method == "POST":
        invalid_fields = []
        email = request.form["email"]
        password = request.form["password"]
        confirm_pass = request.form["confirm_password"]
        user_email = user.userByEmail(email)

        if user_email is None:
            invalid_fields.append(
                {
                    "status": "fail",
                    "message": "This email address is not on file, click register",
                }
            )
        if len(password) < 4:
            invalid_fields.append(
                {
                    "id": "password",
                    "message": "Password length should be not be less than four characters",
                }
            )
        if password != confirm_pass:
            invalid_fields.append(
                {"id": "confirm_password", "message": "Passwords must match!"}
            )
        hashed_string = hashlib.sha256()
        hashed_string.update((salt + password).encode("utf-8"))
        hashed_pass = hashed_string.hexdigest()

        if len(invalid_fields) == 0:
            user.resetPassword(user_email[0], hashed_pass)
            return {
                "status": "success",
                "message": "Your password has been updated to your new password",
            }

    return render_template("reset_password.html")


# this is form submission version verification
@app.route("/verification_code", methods=["GET", "POST"])
def emailVerification():
    if request.method == "POST":
        invalid_field = []
        verification = request.form["verification"]
        user_code = user.getVerificationCode(verification)

        if user_code[4] != verification:
            invalid_field.append({"id": "verification", "message": "Invalid Code"})
        if len(invalid_field) == 0:
            user.isVerified(user_code[0], True)

            return redirect(url_for("login"))

    return render_template("verification_code.html")


@app.route("/form_login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        invalid_fields = []
        user_account = user.getByUsername(request.form["username"])
        if user_account is None:
            invalid_fields.append(
                {"id": "username", "message": "Username does not exist"}
            )
        hashed_string = hashlib.sha256()
        hashed_string.update((salt + request.form["password"]).encode("utf-8"))
        hashed_pass = hashed_string.hexdigest()

        if user_account is not None and user_account[3] != hashed_pass:
            invalid_fields.append(
                {"id": "password", "message": "Password is not valid"}
            )

        if len(invalid_fields) == 0:
            session["username"] = request.form["username"]
            session["password"] = request.form["password"]

        return {
            "status": "success" if len(invalid_fields) == 0 else "fail",
            "invalid_fields": invalid_fields,
        }
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, threaded=True)
