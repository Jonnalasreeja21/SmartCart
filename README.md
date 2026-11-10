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
- Order history, order confirmation, and invoice pages

Payment and email flows require valid provider credentials and external service configuration. They are not available as an offline demo.

## Stack

- Python and Flask
- MySQL
- Flask-Mail
- bcrypt
- Razorpay Python SDK
- xhtml2pdf
- python-dotenv
- HTML, CSS, and JavaScript templates

## Repository layout

```text
SmartCart/
├── app.py
├── config.py
├── .env.example
├── requirements.txt
├── schema.sql
├── templates/
├── static/
└── utils/
    └── pdf_generator.py
```

## Prerequisites

- Python 3.10 or newer
- MySQL Server
- Razorpay credentials for checkout
- SMTP credentials for email and OTP flows

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

3. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Create the local environment file by copying `.env.example` to `.env`. Generate a unique Flask key with:

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

   Put the generated value in `SECRET_KEY` in `.env`, then fill in your MySQL, SMTP, and Razorpay settings. The default database name is `smartcart_db`.

5. Create the database tables:

   ```bash
   mysql -u root -p < schema.sql
   ```

   This is an initial schema based on the queries in the current application. Review it before applying it to an existing database. If you change `DB_NAME`, update the database name in `schema.sql` as well.

6. Start the development server:

   ```bash
   python app.py
   ```

   Open [http://127.0.0.1:5000](http://127.0.0.1:5000). Flask debug mode is disabled by default.

## Configuration and security

The application reads settings from environment variables; `.env` is loaded for local development and ignored by Git. Never commit real passwords, API secrets, or Flask secret keys. Credentials that were committed previously may remain in Git history: revoke or rotate any real SMTP and Razorpay credentials with their providers. Changing this repository does not invalidate exposed credentials. Use Razorpay test credentials while developing, and deploy behind a production WSGI server rather than Flask's built-in server.

## License

No license file is currently included. Contact the repository owner before reusing or redistributing this project.
