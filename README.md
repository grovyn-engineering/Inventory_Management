# Inventory Management System

Inventory Management System is a Django-based application designed to manage products, stock levels, orders, financial records, notifications, and user operations from a centralized platform.

Features

* Product Management

  * Add, update, and manage products
  * Track stock quantities
  * Low-stock monitoring
  * Inventory adjustments

* Order Management

  * Create and manage orders
  * Track order status
  * Maintain order history

* Finance Management

  * Record financial transactions
  * Track income and expenses
  * Payment integration support

* User Management

  * Custom user authentication
  * Role-based access control
  * JWT authentication

* Notifications

  * Low stock alerts
  * Product expiry alerts
  * WhatsApp notification support

* API Support

  * REST APIs using Django REST Framework
  * JWT secured endpoints
  * Swagger/OpenAPI documentation

Technology Stack

* Python 3
* Django
* Django REST Framework
* Simple JWT
* SQLite
* Cloudinary
* Razorpay
* drf-spectacular
* WhiteNoise
* django-cors-headers

Project Structure

```text
Inventory_Management/
│
├── common/
├── finance/
├── inventory/
├── inventory_automation/
├── notifications/
├── orders/
├── users/
├── templates/
├── media/
├── manage.py
└── build.sh
```

Getting Started

Clone the repository

```bash
git clone https://github.com/grovyn-engineering/Inventory_Management.git
cd Inventory_Management
```

Create a virtual environment

```bash
python -m venv venv
```

Activate the environment

Windows

```bash
venv\Scripts\activate
```

Linux / macOS

```bash
source venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

Create a `.env` file

```env
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret

LOW_STOCK_THRESHOLD=5
EXPIRY_ALERT_DAYS=2

WHATSAPP_API_URL=
WHATSAPP_API_TOKEN=
WHATSAPP_FROM_NUMBER=
WHATSAPP_TIMEOUT_SECONDS=8
```

Run migrations

```bash
python manage.py migrate
```

Create an admin account

```bash
python manage.py createsuperuser
```

Start the development server

```bash
python manage.py runserver
```

Application URL

```text
http://127.0.0.1:8000/
```

API Documentation

Available after running the server.

```text
/api/schema/
/api/docs/
```

Authentication

Supported authentication methods:

* Session Authentication
* JWT Authentication

Authorization header format:

```http
Authorization: Bearer <access_token>
```

Third-Party Integrations

Cloudinary

Used for media file storage.

Required configuration:

```env
CLOUDINARY_CLOUD_NAME
CLOUDINARY_API_KEY
CLOUDINARY_API_SECRET
```

Razorpay

Used for payment processing.

Required configuration:

```env
RAZORPAY_KEY_ID
RAZORPAY_KEY_SECRET
RAZORPAY_WEBHOOK_SECRET
```

WhatsApp Notifications

Used for:

* Low stock alerts
* Expiry reminders
* Business notifications

Deployment Notes

* Set DEBUG=False
* Configure production database
* Configure ALLOWED_HOSTS
* Store secrets in environment variables
* Configure static and media file hosting

Contributing

1. Fork the repository
2. Create a feature branch
3. Commit changes
4. Push to your branch
5. Create a pull request

License

MIT License

Developed by Grovyn Engineering.
