from flask import Flask, render_template, request, redirect, session, flash,url_for,jsonify
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from flask import make_response
from utils.pdf_generator import generate_pdf
import sqlite3
import bcrypt
import random
import config
import os
from werkzeug.utils import secure_filename
import razorpay
import traceback
app = Flask(__name__)
app.secret_key = config.SECRET_KEY

razorpay_client = razorpay.Client(
    auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET)
)


# ---------------- EMAIL CONFIGURATION ----------------
app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = config.MAIL_PASSWORD

mail = Mail(app)

serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])


# ---------------- DB CONNECTION FUNCTION --------------
def get_db_connection():
    """Open a SQLite connection with dictionary-like rows and FK enforcement."""
    conn = sqlite3.connect(config.DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------
# ROUTE 1: ADMIN SIGNUP (SEND OTP)
# ---------------------------------------------------------
@app.route('/')
def home():
    return render_template('home.html')
@app.route('/admin-signup', methods=['GET', 'POST'])
def admin_signup():

    # Show form
    if request.method == "GET":
        return render_template("admin/admin_signup.html")

    # POST → Process signup
    name = request.form['name']
    email = request.form['email']

    # 1️⃣ Check if admin email already exists
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT admin_id FROM admin WHERE email=?", (email,))
    existing_admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if existing_admin:
        flash("This email is already registered. Please login instead.", "danger")
        return redirect('/admin-signup')

    # 2️⃣ Save user input temporarily in session
    session['signup_name'] = name
    session['signup_email'] = email

    # 3️⃣ Generate OTP and store in session
    otp = random.randint(100000, 999999)
    session['otp'] = otp

    # 4️⃣ Send OTP Email
    message = Message(
        subject="SmartCart Admin OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    message.body = f"Your OTP for SmartCart Admin Registration is: {otp}"
    mail.send(message)

    flash("OTP sent to your email!", "success")
    return redirect('/verify-otp')



# ---------------------------------------------------------
# ROUTE 2: DISPLAY OTP PAGE
# ---------------------------------------------------------
@app.route('/verify-otp', methods=['GET'])
def verify_otp_get():
    return render_template("admin/verify_otp.html")



# ---------------------------------------------------------
# ROUTE 3: VERIFY OTP + SAVE ADMIN
# ---------------------------------------------------------
@app.route('/verify-otp', methods=['POST'])
def verify_otp_post():
    
    # User submitted OTP + Password
    user_otp = request.form['otp']
    password = request.form['password']

    # Compare OTP
    if str(session.get('otp')) != str(user_otp):
        flash("Invalid OTP. Try again!", "danger")
        return redirect('/verify-otp')

    # Hash password using bcrypt
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    # Insert admin into database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO admin (name, email, password) VALUES (?, ?, ?)",
        (session['signup_name'], session['signup_email'], hashed_password)
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Clear temporary session data
    session.pop('otp', None)
    session.pop('signup_name', None)
    session.pop('signup_email', None)

    flash("Admin Registered Successfully!", "success")
    return redirect('/admin-signup')


# =================================================================
# ROUTE 4: ADMIN LOGIN PAGE (GET + POST)
# =================================================================
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():

    # Show login page
    if request.method == 'GET':
        return render_template("admin/admin_login.html")

    # POST → Validate login
    email = request.form['email']
    password = request.form['password']

    # Step 1: Check if admin email exists
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM admin WHERE email=?", (email,))
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    if admin is None:
        flash("Email not found! Please register first.", "danger")
        return redirect('/admin-login')

    # Step 2: Compare entered password with hashed password
    # Compare entered password with stored bcrypt hash

    stored_password = admin['password']

    if isinstance(stored_password, str):
        stored_password = stored_password.encode('utf-8')

    if not bcrypt.checkpw(
        password.encode('utf-8'),
        stored_password
    ):
        flash("Incorrect password! Try again.", "danger")
        return redirect('/admin-login')

    # Step 5: If login success → Create admin session
    session['admin_id'] = admin['admin_id']
    session['admin_name'] = admin['name']
    session['admin_email'] = admin['email']

    flash("Login Successful!", "success")
    return redirect('/admin-dashboard')



# =================================================================
# ROUTE 5: ADMIN DASHBOARD (PROTECTED ROUTE)
# =================================================================
@app.route('/admin-dashboard')
def admin_dashboard():

    # Protect dashboard → Only logged-in admin can access
    if 'admin_id' not in session:
        flash("Please login to access dashboard!", "danger")
        return redirect('/admin-login')

    # Send admin name to dashboard UI
    return render_template("admin/dashboard.html", admin_name=session['admin_name'])



# =================================================================
# ROUTE 6: ADMIN LOGOUT
# =================================================================
@app.route('/admin-logout')
def admin_logout():

    # Clear admin session
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    session.pop('admin_email', None)

    flash("Logged out successfully.", "success")
    return redirect('/admin-login')

# ------------------- IMAGE UPLOAD PATH -------------------
UPLOAD_FOLDER = 'static/uploads/product_images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ROUTE 7: SHOW ADD PRODUCT PAGE (Protected Route)
# =================================================================
@app.route('/admin/add-item', methods=['GET'])
def add_item_page():

    # Only logged-in admin can access
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    return render_template("admin/add_item.html")



# =================================================================
# ROUTE 8: ADD PRODUCT INTO DATABASE
# =================================================================
@app.route('/admin/add-item', methods=['POST'])
def add_item():

    # Check admin session
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    # 1️⃣ Get form data
    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']
    image_file = request.files['image']

    # 2️⃣ Validate image upload
    if image_file.filename == "":
        flash("Please upload a product image!", "danger")
        return redirect('/admin/add-item')

    # 3️⃣ Secure the file name
    filename = secure_filename(image_file.filename)

    # 4️⃣ Create full path
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    # 5️⃣ Save image into folder
    image_file.save(image_path)

    # 6️⃣ Insert product into database
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
    """INSERT INTO products
    (name, description, category, price, image, admin_id)
    VALUES (?, ?, ?, ?, ?, ?)""",
    (name, description, category, price, filename, session['admin_id'])
)

    conn.commit()
    cursor.close()
    conn.close()

    flash("Product added successfully!", "success")
    return redirect('/admin/add-item')

# =================================================================
# ROUTE 09 :UPDATED PRODUCT LIST WITH SEARCH + CATEGORY FILTER
# =================================================================
@app.route('/admin/item-list')
def item_list():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1️⃣ Fetch category list for dropdown
    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    # 2️⃣ Build dynamic query based on filters
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE ?"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category = ?"
        params.append(category_filter)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin/item_list.html",
        products=products,
        categories=categories
    )




#=================================================================
# ROUTE 10: VIEW SINGLE PRODUCT DETAILS
# =================================================================
@app.route('/admin/view-item/<int:item_id>')
def view_item(item_id):

    # Check admin session
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id = ?", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/view_item.html", product=product)
@app.route('/admin/update-item/<int:item_id>', methods=['GET'])
def update_item_page(item_id):

    # Check login
    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    # Fetch product data
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id = ?", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/update_item.html", product=product)

# ROUTE-12: UPDATE PRODUCT + OPTIONAL IMAGE REPLACE
# =================================================================
@app.route('/admin/update-item/<int:item_id>', methods=['POST'])
def update_item(item_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    # 1️⃣ Get updated form data
    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']

    new_image = request.files['image']

    # 2️⃣ Fetch old product data
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE product_id = ?", (item_id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    old_image_name = product['image']

    # 3️⃣ If admin uploaded a new image → replace it
    if new_image and new_image.filename != "":
        
        # Secure filename
        from werkzeug.utils import secure_filename
        new_filename = secure_filename(new_image.filename)

        # Save new image
        new_image_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
        new_image.save(new_image_path)

        # Delete old image file
        old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], old_image_name)
        if os.path.exists(old_image_path):
            os.remove(old_image_path)

        final_image_name = new_filename

    else:
        # No new image uploaded → keep old one
        final_image_name = old_image_name

    # 4️⃣ Update product in the database
    cursor.execute("""
        UPDATE products
        SET name=?, description=?, category=?, price=?, image=?
        WHERE product_id=?
    """, (name, description, category, price, final_image_name, item_id))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Product updated successfully!", "success")
    return redirect('/admin/item-list')

# =========================================================
# ROUTE 13: DELETE PRODUCT SAFELY
# =========================================================

@app.route('/admin/delete-item/<int:item_id>', methods=['POST'])
def delete_item(item_id):

    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect(url_for('admin_login'))

    conn = None
    cursor = None
    image_name = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Check whether product exists
        cursor.execute(
            "SELECT product_id, image FROM products WHERE product_id = ?",
            (item_id,)
        )

        product = cursor.fetchone()

        if not product:
            flash("Product not found!", "danger")
            return redirect(url_for('item_list'))

        image_name = product['image']

        # 2. Check whether product is linked to existing orders
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM order_items
            WHERE product_id = ?
            """,
            (item_id,)
        )

        result = cursor.fetchone()

        if result['total'] > 0:

            flash(
                "This product cannot be deleted because it is linked "
                "to existing orders. Order history is protected.",
                "warning"
            )

            return redirect(url_for('item_list'))

        # 3. Delete product from database
        cursor.execute(
            "DELETE FROM products WHERE product_id = ?",
            (item_id,)
        )

        conn.commit()

        # 4. Delete image only after successful database deletion
        if image_name:
            image_path = os.path.join(
                app.root_path,
                app.config['UPLOAD_FOLDER'],
                image_name
            )

            if os.path.isfile(image_path):
                try:
                    os.remove(image_path)
                except OSError:
                    app.logger.exception(
                        "Product deleted, but image could not be removed: ?",
                        image_path
                    )

        flash("Product deleted successfully!", "success")

    except Exception:

        if conn:
            conn.rollback()

        app.logger.exception(
            "Product deletion failed for product ID: ?",
            item_id
        )

        flash(
            "Unable to delete product. Please try again.",
            "danger"
        )

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()

    return redirect(url_for('item_list'))

# =================================================================
# ROUTE 14: SHOW ADMIN PROFILE DATA
# =================================================================
@app.route('/admin/profile', methods=['GET'])
def admin_profile():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM admin WHERE admin_id = ?", (admin_id,))
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template("admin/admin_profile.html", admin=admin)

# =========================================================
# ROUTE 14: ACTIVATE / DEACTIVATE PRODUCT
# =========================================================

@app.route('/admin/toggle-product/<int:item_id>', methods=['POST'])
def toggle_product_status(item_id):

    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect(url_for('admin_login'))

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT product_id, name, is_active
            FROM products
            WHERE product_id = ?
            """,
            (item_id,)
        )

        product = cursor.fetchone()

        if not product:
            flash("Product not found!", "danger")
            return redirect(url_for('item_list'))

        new_status = 0 if product['is_active'] else 1

        cursor.execute(
            """
            UPDATE products
            SET is_active = ?
            WHERE product_id = ?
            """,
            (new_status, item_id)
        )

        conn.commit()

        if new_status == 1:
            flash("Product activated successfully!", "success")
        else:
            flash("Product deactivated successfully!", "success")

    except Exception:
        if conn:
            conn.rollback()

        app.logger.exception(
            "Product status update failed for ID: ?",
            item_id
        )

        flash("Unable to update product status.", "danger")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return redirect(url_for('item_list'))
# =================================================================
# ROUTE 15: UPDATE ADMIN PROFILE (NAME, EMAIL, PASSWORD, IMAGE)
# =================================================================
@app.route('/admin/profile', methods=['POST'])
def admin_profile_update():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    # 1️⃣ Get form data
    name = request.form['name']
    email = request.form['email']
    new_password = request.form['password']
    new_image = request.files['profile_image']

    conn = get_db_connection()
    cursor = conn.cursor()

    # 2️⃣ Fetch old admin data
    cursor.execute("SELECT * FROM admin WHERE admin_id = ?", (admin_id,))
    admin = cursor.fetchone()

    old_image_name = admin['profile_image']

    # 3️⃣ Update password only if entered
    if new_password:
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    else:
        hashed_password = admin['password']  # keep old password

    # 4️⃣ Process new profile image if uploaded
    if new_image and new_image.filename != "":
        
        from werkzeug.utils import secure_filename
        new_filename = secure_filename(new_image.filename)

        # Save new image
        image_path = os.path.join(app.config['ADMIN_UPLOAD_FOLDER'], new_filename)
        new_image.save(image_path)

        # Delete old image
        if old_image_name:
            old_image_path = os.path.join(app.config['ADMIN_UPLOAD_FOLDER'], old_image_name)
            if os.path.exists(old_image_path):
                os.remove(old_image_path)

        final_image_name = new_filename
    else:
        final_image_name = old_image_name

    # 5️⃣ Update database
    cursor.execute("""
        UPDATE admin
        SET name=?, email=?, password=?, profile_image=?
        WHERE admin_id=?
    """, (name, email, hashed_password, final_image_name, admin_id))

    conn.commit()
    cursor.close()
    conn.close()

    # Update session name for UI consistency
    session['admin_name'] = name  
    session['admin_email'] = email

    flash("Profile updated successfully!", "success")
    return redirect('/admin/profile')


# =========================================================
# ADMIN FORGOT PASSWORD
# =========================================================

@app.route('/admin/forgot-password', methods=['GET', 'POST'])
def forgot_password():

    if request.method == 'POST':

        email = request.form.get('email', '').strip().lower()

        if not email:
            flash('Please enter your email address.', 'danger')
            return redirect(url_for('forgot_password'))

        conn = None
        cursor = None

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT * FROM admin WHERE email = ?",
                (email,)
            )

            admin = cursor.fetchone()

            if admin:
                token = serializer.dumps(
                    email,
                    salt='password-reset'
                )

                reset_url = url_for(
                    'reset_password',
                    token=token,
                    _external=True
                )

                msg = Message(
                    subject="SmartCart - Password Reset",
                    sender=config.MAIL_USERNAME,
                    recipients=[email]
                )

                msg.body = f"""Hello {admin['name']},

Click the link below to reset your SmartCart password:

{reset_url}

This link expires in 15 minutes.

If you did not request this, ignore this email.
"""

                mail.send(msg)

        except Exception:
            app.logger.exception(
                "Admin password reset email failed"
            )

        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

        flash(
            'If your email is registered, a reset link has been sent.',
            'success'
        )

        return redirect(url_for('forgot_password'))

    return render_template('admin/forget_password.html')


# =========================================================
# ADMIN RESET PASSWORD
# =========================================================

@app.route('/admin/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):

    try:
        email = serializer.loads(
            token,
            salt='password-reset',
            max_age=900
        )

    except Exception:
        flash(
            'Invalid or expired reset link!',
            'danger'
        )
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':

        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not password or not confirm_password:
            flash('Please fill in both password fields.', 'danger')
            return redirect(
                url_for('reset_password', token=token)
            )

        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return redirect(
                url_for('reset_password', token=token)
            )

        if len(password) < 8:
            flash(
                'Password must contain at least 8 characters.',
                'danger'
            )
            return redirect(
                url_for('reset_password', token=token)
            )

        hashed_password = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        conn = None
        cursor = None

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE admin SET password = ? WHERE email = ?",
                (hashed_password, email)
            )

            if cursor.rowcount == 0:
                flash('Admin account not found.', 'danger')
                return redirect(url_for('admin_login'))

            conn.commit()

            flash(
                'Password reset successfully! Please log in.',
                'success'
            )

            return redirect(url_for('admin_login'))

        except Exception:
            if conn:
                conn.rollback()

            app.logger.exception(
                "Admin password update failed"
            )

            flash(
                'Unable to reset password. Please try again.',
                'danger'
            )

        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template(
        'admin/reset_password.html',
        token=token
    )

# =========================================================
# USER FORGOT PASSWORD
# =========================================================
@app.route('/user/forget-password', methods=['GET', 'POST'])
def user_forgot_password():

    if request.method == 'POST':
        email = request.form.get('email', '').strip()

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT name FROM users WHERE email = ?", (email,))
            user = cursor.fetchone()

            # Always show the same response to avoid revealing registered emails.
            if user:
                token = serializer.dumps(email, salt='user-password-reset')
                reset_url = url_for(
                    'user_reset_password',
                    token=token,
                    _external=True
                )

                msg = Message(
                    subject="SmartCart - User Password Reset",
                    sender=config.MAIL_USERNAME,
                    recipients=[email]
                )
                msg.body = f"""Hello {user['name']},

Use the link below to reset your SmartCart password:

{reset_url}

This link expires in 15 minutes. If you did not request this, ignore this email.
"""
                mail.send(msg)
        finally:
            cursor.close()
            conn.close()

        flash(
            'If your email is registered, a password reset link has been sent.',
            'success'
        )
        return redirect(url_for('user_forgot_password'))

    return render_template('user/user_forget_password.html')


# =========================================================
# USER RESET PASSWORD
# =========================================================
@app.route('/user/reset-password/<token>', methods=['GET', 'POST'])
def user_reset_password(token):

    try:
        email = serializer.loads(
            token,
            salt='user-password-reset',
            max_age=900
        )
    except Exception:
        flash('Invalid or expired reset link. Please request a new one.', 'danger')
        return redirect(url_for('user_forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('user_reset_password', token=token))

        if len(password) < 8:
            flash('Password must contain at least 8 characters.', 'danger')
            return redirect(url_for('user_reset_password', token=token))

        hashed_password = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "UPDATE users SET password = ? WHERE email = ?",
                (hashed_password, email)
            )
            if cursor.rowcount == 0:
                flash('User account not found. Please request a new reset link.', 'danger')
                return redirect(url_for('user_forgot_password'))

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

        flash('Your password has been reset successfully. Please login.', 'success')
        return redirect(url_for('user_login'))

    return render_template('user/user_reset_password.html', token=token)


# =================================================================
# ROUTE: USER REGISTRATION
# =================================================================
@app.route('/user-register', methods=['GET', 'POST'])
def user_register():

    if request.method == 'GET':
        return render_template("user/user_register.html")

    name = request.form['name']
    email = request.form['email']
    password = request.form['password']

    # Check if user already exists
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    existing_user = cursor.fetchone()

    if existing_user:
        flash("Email already registered! Please login.", "danger")
        return redirect('/user-register')

    # Hash password
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    # Insert new user
    cursor.execute(
        "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
        (name, email, hashed_password)
    )
    conn.commit()

    cursor.close()
    conn.close()

    flash("Registration successful! Please login.", "success")
    return redirect('/user-login')
# =================================================================
# ROUTE: USER LOGIN
# =================================================================
@app.route('/user-login', methods=['GET', 'POST'])
def user_login():

    if request.method == 'GET':
        return render_template("user/user_login.html")

    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if not user:
        flash("Email not found! Please register.", "danger")
        return redirect('/user-login')

    # Verify password
    if not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
        flash("Incorrect password!", "danger")
        return redirect('/user-login')

    # Create user session
    session['user_id'] = user['user_id']
    session['user_name'] = user['name']
    session['user_email'] = user['email']

    flash("Login successful!", "success")
    return redirect('/user-dashboard')
# ROUTE: USER DASHBOARD
@app.route('/user-dashboard')
def user_dashboard():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    return render_template("user/user_home.html", user_name=session['user_name'])

# =================================================================
# ROUTE: USER LOGOUT
# =================================================================
@app.route('/user-logout')
def user_logout():
    
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_email', None)

    flash("Logged out successfully!", "success")
    return redirect('/user-login')

# ROUTE: USER PRODUCT LISTING (SEARCH + FILTER)

# =================================================================
# USER PRODUCTS - DISPLAY ACTIVE PRODUCTS ONLY
# =================================================================

@app.route('/user/products')
def user_products():

    # Check user login
    if 'user_id' not in session:
        flash("Please login to view products!", "danger")
        return redirect('/user-login')

    search = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch categories from active products only
        cursor.execute("""
            SELECT DISTINCT category
            FROM products
            WHERE is_active = 1
            ORDER BY category
        """)

        categories = cursor.fetchall()

        # Fetch active products only
        query = """
            SELECT *
            FROM products
            WHERE is_active = 1
        """

        params = []

        # Product search
        if search:
            query += " AND name LIKE ?"
            params.append("%" + search + "%")

        # Category filtering
        if category_filter:
            query += " AND category = ?"
            params.append(category_filter)

        query += " ORDER BY product_id DESC"

        cursor.execute(query, params)
        products = cursor.fetchall()

        return render_template(
            "user/user_products.html",
            products=products,
            categories=categories
        )

    except Exception:
        app.logger.exception("Error loading customer products")
        flash("Unable to load products. Please try again.", "danger")

        return redirect('/user/dashboard')

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

# =================================================================
# USER PRODUCTS - DISPLAY ACTIVE PRODUCTS ONLY
# =================================================================

@app.route('/user/products')
def user_products():

    # Check user login
    if 'user_id' not in session:
        flash("Please login to view products!", "danger")
        return redirect('/user-login')

    search = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch categories from active products only
        cursor.execute("""
            SELECT DISTINCT category
            FROM products
            WHERE is_active = 1
            ORDER BY category
        """)

        categories = cursor.fetchall()

        # Fetch active products only
        query = """
            SELECT *
            FROM products
            WHERE is_active = 1
        """

        params = []

        # Product search
        if search:
            query += " AND name LIKE ?"
            params.append("%" + search + "%")

        # Category filtering
        if category_filter:
            query += " AND category = ?"
            params.append(category_filter)

        query += " ORDER BY product_id DESC"

        cursor.execute(query, params)
        products = cursor.fetchall()

        return render_template(
            "user/user_products.html",
            products=products,
            categories=categories
        )

    except Exception:
        app.logger.exception("Error loading customer products")
        flash("Unable to load products. Please try again.", "danger")

        return redirect('/user/dashboard')

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

# =================================================================
# ROUTE: USER PRODUCT DETAILS PAGE
# =================================================================
@app.route('/user/product/<int:product_id>')
def user_product_details(product_id):

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products WHERE product_id = ?", (product_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/user/products')

    return render_template("user/product_details.html", product=product)

# =================================================================
# ADD ITEM TO CART
# =================================================================
@app.route('/user/add-to-cart/<int:product_id>')
def add_to_cart(product_id):

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    # Create cart if doesn't exist
    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']

    # Get product
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE product_id=?", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()

    if not product:
        flash("Product not found.", "danger")
        return redirect(request.referrer)

    pid = str(product_id)

    # If exists → increase quantity
    if pid in cart:
        cart[pid]['quantity'] += 1
    else:
        cart[pid] = {
            'name': product['name'],
            'price': float(product['price']),
            'image': product['image'],
            'quantity': 1
        }

    session['cart'] = cart

    flash("Item added to cart!", "success")
    return redirect('/user/cart')    

# =================================================================
# VIEW CART PAGE
# =================================================================
@app.route('/user/cart')
def view_cart():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})

    # Calculate total
    grand_total = sum(item['price'] * item['quantity'] for item in cart.values())

    return render_template("user/cart.html", cart=cart, grand_total=grand_total)

# =================================================================
# INCREASE QUANTITY
# =================================================================
@app.route('/user/cart/increase/<pid>')
def increase_quantity(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart[pid]['quantity'] += 1

    session['cart'] = cart
    session.modified = True
    return redirect('/user/cart')
# =================================================================
# DECREASE QUANTITY
# =================================================================
@app.route('/user/cart/decrease/<pid>')
def decrease_quantity(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart[pid]['quantity'] -= 1

        # If quantity becomes 0 → remove item
        if cart[pid]['quantity'] <= 0:
            cart.pop(pid)

    session['cart'] = cart
    session.modified = True
    return redirect('/user/cart')
#=================================================================
# REMOVE ITEM
# =================================================================
@app.route('/user/cart/remove/<pid>')
def remove_from_cart(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart.pop(pid)

    session['cart'] = cart

    flash("Item removed!", "success")
    return redirect('/user/cart')

# ================================================================
# CHECKOUT - SELECTED PRODUCTS AND SAVED ADDRESSES
# ================================================================

@app.route('/user/checkout', methods=['GET', 'POST'])
def user_checkout():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})

    if request.method == 'POST':

        selected_ids = list(dict.fromkeys(
            request.form.getlist('selected_products')
        ))

        if not selected_ids:
            flash("Please select products!", "warning")
            return redirect('/user/cart')

        if any(pid not in cart for pid in selected_ids):
            flash("Invalid product selection!", "danger")
            return redirect('/user/cart')

        session['selected_products'] = selected_ids
        session.pop('selected_address_id', None)
        session.modified = True

    selected_ids = session.get('selected_products', [])

    if not selected_ids or any(pid not in cart for pid in selected_ids):
        flash("Please select products first!", "warning")
        return redirect('/user/cart')

    selected_products = {}
    selected_total = 0

    for pid in selected_ids:
        item = cart[pid]
        selected_products[pid] = item
        selected_total += float(item['price']) * int(item['quantity'])

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT *
            FROM user_addresses
            WHERE user_id = ?
            ORDER BY id DESC
        """, (session['user_id'],))

        saved_addresses = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    return render_template(
        'user/add_address.html',
        saved_addresses=saved_addresses,
        selected_products=selected_products,
        selected_total=selected_total
    )


# ================================================================
# SAVE DELIVERY ADDRESS
# ================================================================

@app.route('/user/save-address', methods=['POST'])
def save_address():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    selected_ids = session.get('selected_products', [])
    cart = session.get('cart', {})

    if not selected_ids or any(pid not in cart for pid in selected_ids):
        flash("Please select products!", "warning")
        return redirect('/user/cart')

    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()
    city = request.form.get('city', '').strip()
    state = request.form.get('state', '').strip()
    pincode = request.form.get('pincode', '').strip()

    if not all([full_name, phone, address, city, state, pincode]):
        flash("Please fill all address details!", "warning")
        return redirect('/user/checkout')

    if not phone.isdigit() or len(phone) != 10:
        flash("Enter a valid 10-digit phone number!", "warning")
        return redirect('/user/checkout')

    if not pincode.isdigit() or len(pincode) != 6:
        flash("Enter a valid 6-digit PIN code!", "warning")
        return redirect('/user/checkout')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO user_addresses
            (user_id, full_name, phone, address, city, state, pincode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session['user_id'],
            full_name,
            phone,
            address,
            city,
            state,
            pincode
        ))

        address_id = cursor.lastrowid
        conn.commit()

        session['selected_address_id'] = address_id
        session.modified = True

        flash("Address saved successfully!", "success")
        return redirect('/user/order-summary')

    except Exception as e:
        conn.rollback()
        print("Address Error:", e)
        flash("Unable to save address. Please try again.", "danger")
        return redirect('/user/checkout')

    finally:
        cursor.close()
        conn.close()


# ================================================================
# SELECT SAVED DELIVERY ADDRESS
# ================================================================

@app.route('/user/select-address', methods=['POST'])
def select_address():

    if 'user_id' not in session:
        return redirect('/user-login')

    address_id = request.form.get('address_id')

    if not address_id or not address_id.isdigit():
        flash("Invalid address selection!", "danger")
        return redirect('/user/checkout')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id
            FROM user_addresses
            WHERE id = ? AND user_id = ?
        """, (int(address_id), session['user_id']))

        address = cursor.fetchone()

        if not address:
            flash("Invalid address selection!", "danger")
            return redirect('/user/checkout')

        session['selected_address_id'] = address['id']
        session.modified = True

        return redirect('/user/order-summary')

    finally:
        cursor.close()
        conn.close()


# ================================================================
# ORDER SUMMARY
# ================================================================

@app.route('/user/order-summary')
def order_summary():

    if 'user_id' not in session:
        return redirect(url_for('user_login'))

    selected_address_id = session.get('selected_address_id')
    selected_ids = session.get('selected_products', [])
    cart = session.get('cart', {})

    if not selected_address_id:
        flash("Please select a delivery address.", "warning")
        return redirect(url_for('user_checkout'))

    if not selected_ids:
        flash("Please select products first.", "warning")
        return redirect(url_for('user_cart'))

    if any(pid not in cart for pid in selected_ids):
        flash("Invalid product selection.", "danger")
        return redirect(url_for('user_cart'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT *
            FROM user_addresses
            WHERE id = ? AND user_id = ?
        """, (selected_address_id, session['user_id']))

        address = cursor.fetchone()

        if not address:
            flash("Please select a valid address.", "danger")
            return redirect(url_for('user_checkout'))

        placeholders = ','.join(['?'] * len(selected_ids))

        cursor.execute(f"""
            SELECT product_id, name, price
            FROM products
            WHERE product_id IN ({placeholders})
        """, tuple(int(pid) for pid in selected_ids))

        db_products = cursor.fetchall()

        if len(db_products) != len(selected_ids):
            flash("Some products are unavailable.", "danger")
            return redirect(url_for('user_cart'))

        selected_products = {}
        selected_total = 0

        for product in db_products:

            pid = str(product['product_id'])
            quantity = int(cart[pid]['quantity'])
            price = float(product['price'])

            selected_products[pid] = {
                'name': product['name'],
                'price': price,
                'quantity': quantity
            }

            selected_total += price * quantity

        return render_template(
            'user/order_summary.html',
            address=address,
            selected_products=selected_products,
            selected_total=selected_total
        )

    finally:
        cursor.close()
        conn.close()
# ================================================================
# CREATE RAZORPAY ORDER
# ================================================================

@app.route('/user/pay', methods=['POST'])
def user_pay():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})
    selected_ids = session.get('selected_products', [])
    address_id = session.get('selected_address_id')

    if not selected_ids:
        flash("Please select products first!", "warning")
        return redirect('/user/cart')

    if not address_id:
        flash("Please select a delivery address!", "warning")
        return redirect('/user/checkout')

    if not cart:
        flash("Your cart is empty!", "danger")
        return redirect('/user/products')

    selected_ids = list(dict.fromkeys(str(pid) for pid in selected_ids))

    if any(pid not in cart for pid in selected_ids):
        flash("Invalid product selection!", "danger")
        return redirect('/user/cart')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:

        # Verify delivery address
        cursor.execute("""
            SELECT *
            FROM user_addresses
            WHERE id = ? AND user_id = ?
        """, (address_id, session['user_id']))

        delivery_address = cursor.fetchone()

        if not delivery_address:
            flash("Invalid delivery address!", "danger")
            return redirect('/user/checkout')

        # Fetch selected products from database
        placeholders = ','.join(['?'] * len(selected_ids))

        cursor.execute(f"""
            SELECT product_id, name, price
            FROM products
            WHERE product_id IN ({placeholders})
        """, tuple(int(pid) for pid in selected_ids))

        products = cursor.fetchall()

        if len(products) != len(selected_ids):
            flash("Some selected products are unavailable!", "danger")
            return redirect('/user/cart')

        # Calculate total
        total_amount = 0

        for product in products:

            pid = str(product['product_id'])
            quantity = int(cart[pid]['quantity'])

            if quantity <= 0:
                raise ValueError("Invalid product quantity")

            price = float(product['price'])

            total_amount += price * quantity

        if total_amount <= 0:
            raise ValueError("Invalid payment amount")

        razorpay_amount = int(round(total_amount * 100))

        # Create Razorpay order
        razorpay_order = razorpay_client.order.create({
            "amount": razorpay_amount,
            "currency": "INR",
            "payment_capture": "1"
        })

        # Save checkout details in session
        session['razorpay_order_id'] = razorpay_order['id']
        session['payment_amount'] = total_amount

        session.modified = True

        return render_template(
            'user/payment.html',
            amount=total_amount,
            amount_paise=razorpay_amount,
            key_id=config.RAZORPAY_KEY_ID,
            order_id=razorpay_order['id'],
            delivery_address=delivery_address
        )

    except Exception as e:

        print("Payment Error:", e)

        flash(
            "Unable to initiate payment. Please try again.",
            "danger"
        )

        return redirect('/user/cart')

    finally:
        cursor.close()
        conn.close()


# ================================================================
# VERIFY RAZORPAY PAYMENT AND SAVE ORDER
# ================================================================

@app.route('/verify-payment', methods=['POST'])
def verify_payment():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    payment_id = request.form.get('razorpay_payment_id')
    razorpay_order_id = request.form.get('razorpay_order_id')
    signature = request.form.get('razorpay_signature')

    saved_order_id = session.get('razorpay_order_id')
    saved_amount = session.get('payment_amount')

    selected_ids = session.get('selected_products', [])
    address_id = session.get('selected_address_id')
    cart = session.get('cart', {})

    if not all([payment_id, razorpay_order_id, signature]):
        flash("Payment details are missing!", "danger")
        return redirect('/user/cart')

    if razorpay_order_id != saved_order_id:
        flash("Invalid Razorpay order!", "danger")
        return redirect('/user/cart')

    if not selected_ids or not address_id or saved_amount is None:
        flash("Checkout information is missing!", "danger")
        return redirect('/user/cart')

    selected_ids = list(dict.fromkeys(str(pid) for pid in selected_ids))

    if any(pid not in cart for pid in selected_ids):
        flash("Invalid cart products!", "danger")
        return redirect('/user/cart')

    # Verify Razorpay signature
    try:

        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        })

    except Exception as e:

        print("Signature verification error:", e)

        flash("Payment verification failed!", "danger")
        return redirect('/user/cart')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:

        conn.execute('BEGIN')

        # Verify delivery address
        cursor.execute("""
            SELECT id
            FROM user_addresses
            WHERE id = ? AND user_id = ?
        """, (address_id, session['user_id']))

        address = cursor.fetchone()

        if not address:
            raise ValueError("Invalid delivery address")

        # Fetch products from database
        placeholders = ','.join(['?'] * len(selected_ids))

        cursor.execute(f"""
            SELECT product_id, name, price
            FROM products
            WHERE product_id IN ({placeholders})
        """, tuple(int(pid) for pid in selected_ids))

        products = cursor.fetchall()

        if len(products) != len(selected_ids):
            raise ValueError("Some products are unavailable")

        # Calculate total and prepare order items
        total_amount = 0
        order_items_data = []

        for product in products:

            pid = str(product['product_id'])
            quantity = int(cart[pid]['quantity'])

            if quantity <= 0:
                raise ValueError("Invalid product quantity")

            price = float(product['price'])

            total_amount += price * quantity

            order_items_data.append((
                product['product_id'],
                product['name'],
                quantity,
                price
            ))

        expected_amount = int(round(total_amount * 100))

        # Compare with original checkout amount
        saved_amount_paise = int(round(float(saved_amount) * 100))

        if expected_amount != saved_amount_paise:
            raise ValueError("Order amount does not match checkout amount")

        # Fetch payment details from Razorpay
        payment_details = razorpay_client.payment.fetch(payment_id)

        if payment_details['status'] != 'captured':
            raise ValueError("Payment is not captured")

        if payment_details['order_id'] != razorpay_order_id:
            raise ValueError("Payment order mismatch")

        if payment_details['amount'] != expected_amount:
            raise ValueError("Payment amount mismatch")

        if payment_details['currency'] != 'INR':
            raise ValueError("Invalid payment currency")

        # Check duplicate payment
        cursor.execute("""
            SELECT order_id
            FROM orders
            WHERE razorpay_payment_id = ?
        """, (payment_id,))

        existing_order = cursor.fetchone()

        if existing_order:

            # Do not insert the same payment twice
            conn.commit()

            for pid in selected_ids:
                cart.pop(str(pid), None)

            session['cart'] = cart

            session.pop('selected_products', None)
            session.pop('selected_address_id', None)
            session.pop('razorpay_order_id', None)
            session.pop('payment_amount', None)

            session.modified = True

            return redirect(
                url_for(
                    'order_success',
                    order_db_id=existing_order['order_id']
                )
            )

        # Insert order into orders table
        cursor.execute("""
            INSERT INTO orders
            (
                user_id,
                address_id,
                razorpay_order_id,
                razorpay_payment_id,
                amount,
                payment_status
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            session['user_id'],
            address_id,
            razorpay_order_id,
            payment_id,
            total_amount,
            'paid'
        ))

        order_db_id = cursor.lastrowid

        # Insert purchased products into order_items
        for item in order_items_data:

            cursor.execute("""
                INSERT INTO order_items
                (
                    order_id,
                    product_id,
                    product_name,
                    quantity,
                    price
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                order_db_id,
                item[0],
                item[1],
                item[2],
                item[3]
            ))

        # Commit database transaction
        conn.commit()

        # Remove purchased products only
        for pid in selected_ids:
            cart.pop(str(pid), None)

        session['cart'] = cart

        # Clear temporary checkout data
        session.pop('selected_products', None)
        session.pop('selected_address_id', None)
        session.pop('razorpay_order_id', None)
        session.pop('payment_amount', None)

        session.modified = True

        flash("Payment successful! Your order has been placed.", "success")

        return redirect(
            url_for(
                'order_success',
                order_db_id=order_db_id
            )
        )

    except Exception as e:

        conn.rollback()

        print("Order saving error:", e)

        flash(
            "Payment may have been received, but order saving failed. "
            "Please contact support with your payment ID: " + str(payment_id),
            "danger"
        )

        return redirect('/user/cart')

    finally:

        cursor.close()
        conn.close()


# ================================================================
# ORDER SUCCESS
# ================================================================

@app.route('/user/order-success/<int:order_db_id>')
def order_success(order_db_id):

    if 'user_id' not in session:
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:

        # Fetch order
        cursor.execute("""
            SELECT *
            FROM orders
            WHERE order_id = ? AND user_id = ?
        """, (order_db_id, session['user_id']))

        order = cursor.fetchone()

        if not order:
            flash("Order not found!", "danger")
            return redirect('/user/products')

        # Fetch order items
        cursor.execute("""
            SELECT *
            FROM order_items
            WHERE order_id = ?
        """, (order_db_id,))

        items = cursor.fetchall()

        return render_template(
            'user/order_success.html',
            order=order,
            items=items
        )

    finally:
        cursor.close()
        conn.close()


# ================================================================
# USER MY ORDERS
# ================================================================

@app.route('/user/my-orders')
def my_orders():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            SELECT *
            FROM orders
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (session['user_id'],))

        orders = cursor.fetchall()

        return render_template(
            'user/my_orders.html',
            orders=orders
        )

    finally:
        cursor.close()
        conn.close()

# ----------------------------
# GENERATE INVOICE PDF
# ----------------------------
# ----------------------------
# GENERATE INVOICE
# ----------------------------
@app.route('/download-invoice/<int:order_id>')
def download_invoice(order_id):

    if 'user_id' not in session:
        return redirect(url_for('user_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Fetch order details
        cursor.execute("""
            SELECT *
            FROM orders
            WHERE order_id = ? AND user_id = ?
        """, (order_id, session['user_id']))

        order = cursor.fetchone()

        if not order:
            return "Order not found!", 404

        # 2. Fetch customer details
        cursor.execute("""
            SELECT
                full_name,
                phone,
                address,
                city,
                state,
                pincode
            FROM user_addresses
            WHERE id = ? AND user_id = ?
        """, (order['address_id'], session['user_id']))

        customer = cursor.fetchone()

        if not customer:
            return "Customer address not found!", 404

        # 3. Fetch order items
        cursor.execute("""
            SELECT *
            FROM order_items
            WHERE order_id = ?
        """, (order_id,))

        items = cursor.fetchall()

        # 4. Send all variables to invoice template
        return render_template(
            'user/invoice.html',
            order=order,
            customer=customer,
            items=items
        )

    except Exception as e:
        print("Invoice Error:", e)
        traceback.print_exc()
        return "Unable to generate invoice!", 500

    finally:
        cursor.close()
        conn.close()
# ================================================================
# RUN APPLICATION
# ================================================================

if __name__ == '__main__':
    app.run(debug=False)
