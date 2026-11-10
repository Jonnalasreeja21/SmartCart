# SmartCart

SmartCart is a Flask and MySQL e-commerce application with separate admin and customer workflows. The application code includes product management, a shopping cart, address selection, Razorpay checkout, order history, and invoice pages.

## Features

- Admin signup with email OTP verification, login, profile, and password reset flows
- Admin dashboard for adding, viewing, editing, and deleting products
- Customer registration and login
- Product browsing and product detail pages
- Session-based cart with quantity updates and item removal
- Address management and checkout
- Razorpay order creation and payment signature verification
- Order history, order confirmation, and invoice page

Payment and email flows require valid provider credentials and external service configuration. They are not available as an offline demo.

## Stack

- Python and Flask
- MySQL
- Flask-Mail
- bcrypt
- Razorpay Python SDK
- xhtml2pdf
- HTML, CSS, and JavaScript templates

## Repository layout

```text
SmartCart/
├── app.py
├── config.py
├── templates/
│   ├── admin/
│   └── user/
├── static/
├── utils/
│   └── pdf_generator.py
└── .gitignore
```

## Prerequisites

- Python 3.10 or newer
- MySQL Server
- A Razorpay account for payment checkout
- SMTP credentials for email and OTP flows

The repository currently does not include a `requirements.txt` or a database schema/initialization script. The database named in `config.py` and the tables used by the application must exist before the app can run successfully.

## Local setup

1. Clone the repository and enter its directory:

   ```bash
   git clone https://github.com/Jonnalasreeja21/SmartCart.git
   cd SmartCart
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   ```

   On macOS/Linux:

   ```bash
   source .venv/bin/activate
   ```

   On Windows PowerShell:

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

3. Install the application dependencies:

   ```bash
   python -m pip install Flask Flask-Mail mysql-connector-python bcrypt razorpay xhtml2pdf
   ```

4. Create the MySQL database and tables expected by the application. The schema is not included in this repository yet.

5. Configure the database, SMTP, Flask session, and Razorpay settings before starting the application. These settings are currently read from `config.py`.

6. Start the development server:

   ```bash
   python app.py
   ```

   Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

## Configuration and security

Do not commit real passwords, API secrets, or Flask secret keys. The current `config.py` contains hard-coded credentials; rotate any real credentials that have been committed, then move secrets to environment variables before using the project beyond a local exercise. Use Razorpay test credentials while developing and never run Flask's debug server in production.

## License

No license file is currently included. Contact the repository owner before reusing or redistributing this project.
