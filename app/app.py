import os
import uuid
from datetime import datetime

import boto3
import psycopg2
from botocore.client import Config
from botocore.exceptions import ClientError, BotoCoreError
from flask import Flask, request, redirect, url_for, render_template_string

app = Flask(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {"pdf"}

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

def db_connection():
    return psycopg2.connect(
        host=os.environ["PG_HOST"],
        port=os.getenv("PG_PORT", "5432"),
        dbname=os.environ["PG_DB"],
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASS"],
        connect_timeout=5,
    )

def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
        verify=False,
    )

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )

def initialize_database():
    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    price NUMERIC(10, 2) NOT NULL
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    customer TEXT NOT NULL,
                    product_id INTEGER REFERENCES products(id),
                    invoice_key TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cur.execute("SELECT COUNT(*) FROM products")
            count = cur.fetchone()[0]

            if count == 0:
                cur.execute(
                    """
                    INSERT INTO products (name, price)
                    VALUES
                        ('Nutanix Kubernetes Platform', 9999.00),
                        ('Nutanix Database Service', 7499.00),
                        ('Nutanix Objects Storage', 3999.00)
                    """
                )

        conn.commit()
    finally:
        conn.close()

def load_products():
    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, price
                FROM products
                ORDER BY id
                """
            )
            return cur.fetchall()
    finally:
        conn.close()

def load_orders():
    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    o.id,
                    o.customer,
                    p.name,
                    p.price,
                    o.invoice_key,
                    o.created_at
                FROM orders o
                JOIN products p ON p.id = o.product_id
                ORDER BY o.created_at DESC
                LIMIT 20
                """
            )
            return cur.fetchall()
    finally:
        conn.close()

HTML = """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NutaShop</title>
  <style>
    :root {
      --navy: #4c1d95;
      --blue: #6d28d9;
      --cyan: #a855f7;
      --green: #16a66a;
      --bg: #faf7ff;
      --text: #24113f;
      --muted: #76658c;
      --border: #eadcff;
        }
    }

    * { box-sizing:border-box; }

    body {
      margin:0;
      font-family:Inter,system-ui,sans-serif;
      color:var(--text);
      background:var(--bg);
    }

    nav {
      height:68px;
      display:flex;
      justify-content:space-between;
      align-items:center;
      padding:0 7%;
      color:white;
      background:var(--navy);
    }

    .logo { font-size:24px; font-weight:800; }
    .logo span { color:var(--cyan); }

    nav a {
      margin-left:28px;
      color:#d7e6ed;
      text-decoration:none;
      font-size:14px;
    }

    .hero {
      padding:70px 7%;
      color:white;
      background:linear-gradient(120deg,#3b0764,#7e22ce);
    }

    .hero h1 {
      max-width:650px;
      margin:0 0 18px;
      font-size:clamp(38px,5vw,64px);
      line-height:1.02;
      letter-spacing:-2px;
    }

    .hero p {
      max-width:560px;
      margin:0;
      color:#dceff3;
      font-size:18px;
    }

    .container {
      width:min(1160px,86%);
      margin:36px auto 70px;
    }

    .section-title {
      display:flex;
      justify-content:space-between;
      align-items:end;
      margin-bottom:18px;
    }

    h2 { margin:0; font-size:28px; }
    .muted { color:var(--muted); }

    .products {
      display:grid;
      grid-template-columns:repeat(3,1fr);
      gap:18px;
      margin-bottom:36px;
    }

    .product,
    .panel {
      padding:24px;
      background:white;
      border:1px solid var(--border);
      border-radius:18px;
      box-shadow:0 10px 28px rgba(7,27,47,.07);
    }

    .product-icon {
      width:48px;
      height:48px;
      display:grid;
      place-items:center;
      margin-bottom:20px;
      border-radius:14px;
      color:white;
      background:linear-gradient(135deg,#6d28d9,#c084fc);
      font-size:22px;
    }

    .product h3 { margin:0 0 8px; }
    .product p { min-height:48px; color:var(--muted); }

    .price {
      margin:20px 0;
      color:var(--blue);
      font-size:22px;
      font-weight:800;
    }

    .content {
      display:grid;
      grid-template-columns:1fr 1fr;
      gap:24px;
    }

    label {
      display:block;
      margin:16px 0 7px;
      color:var(--muted);
      font-size:13px;
      font-weight:700;
    }

    input, select {
      width:100%;
      padding:13px;
      border:1px solid var(--border);
      border-radius:10px;
      background:#fbfdff;
      font:inherit;
    }

    button {
      width:100%;
      margin-top:22px;
      padding:14px;
      border:0;
      border-radius:10px;
      color:white;
      background:var(--green);
      font:inherit;
      font-weight:800;
      cursor:pointer;
    }

    button:hover { filter:brightness(.95); }

    .order {
      padding:16px 0;
      border-bottom:1px solid var(--border);
    }

    .order:last-child { border-bottom:0; }

    .order-head {
      display:flex;
      justify-content:space-between;
      gap:15px;
    }

    .order small {
      display:block;
      margin-top:6px;
      color:var(--muted);
    }

    @media(max-width:800px) {
      .products,.content { grid-template-columns:1fr; }
      nav { padding:0 5%; }
      nav a { margin-left:12px; }
      .container { width:92%; }
      .hero { padding:52px 5%; }
    }
  </style>
</head>
<body>
  <nav>
    <div class="logo">Nuta<span>Shop</span></div>
    <div>
      <a href="/">Accueil</a>
      <a href="#catalogue">Catalogue</a>
      <a href="#commandes">Mes commandes</a>
    </div>
  </nav>

  <header class="hero">
    <h1>Des solutions simples pour faire avancer votre entreprise.</h1>
    <p>
      Découvrez notre sélection de solutions professionnelles et
      passez commande en quelques clics.
    </p>
  </header>

  <main class="container">
    <section id="catalogue">
      <div class="section-title">
        <h2>Notre catalogue</h2>
        <span class="muted">Solutions professionnelles</span>
      </div>

      <div class="products">
        {% for product in products %}
        <article class="product">
          <div class="product-icon">✦</div>
          <h3>{{ product[1] }}</h3>
          <p>Une solution professionnelle conçue pour votre entreprise.</p>
          <div class="price">{{ "%.2f"|format(product[2]) }} €</div>
        </article>
        {% endfor %}
      </div>
    </section>

    <section class="content">
      <div class="panel">
        <h2>Finaliser une commande</h2>
        <p class="muted">Transmettez vos informations et votre justificatif.</p>

        <form action="/order" method="post" enctype="multipart/form-data">
          <label for="customer">Nom du client</label>
          <input id="customer" name="customer"
                 placeholder="Entreprise ACME" required>

          <label for="product_id">Produit</label>
          <select id="product_id" name="product_id" required>
            {% for product in products %}
            <option value="{{ product[0] }}">
              {{ product[1] }} — {{ "%.2f"|format(product[2]) }} €
            </option>
            {% endfor %}
          </select>

          <label for="file">Justificatif ou facture PDF</label>
          <input id="file" name="file" type="file"
                 accept=".pdf,application/pdf" required>

          <button type="submit">Confirmer la commande</button>
        </form>
      </div>

      <div class="panel" id="commandes">
        <h2>Mes commandes</h2>
        <p class="muted">Retrouvez ici vos dernières commandes.</p>

        {% if orders %}
          {% for order in orders %}
          <div class="order">
            <div class="order-head">
              <strong>Commande #{{ order[0] }}</strong>
              <strong>{{ "%.2f"|format(order[3]) }} €</strong>
            </div>
            <small>{{ order[1] }} · {{ order[2] }}</small>
            <small>Document : {{ order[4] }}</small>
          </div>
          {% endfor %}
        {% else %}
          <p class="muted">Aucune commande enregistrée.</p>
        {% endif %}
      </div>
    </section>
  </main>
</body>
</html>
"""

@app.route("/")
def index():
    try:
        return render_template_string(
            HTML,
            products=load_products(),
            orders=load_orders(),
        )
    except Exception:
        app.logger.exception("Erreur lors du chargement de la page")
        return "Service temporairement indisponible", 503

@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/order", methods=["POST"])
def create_order():
    customer = request.form.get("customer", "").strip()
    product_id = request.form.get("product_id")
    uploaded_file = request.files.get("file")

    if not customer or not product_id or not uploaded_file:
        return "Informations de commande incomplètes", 400

    if not allowed_file(uploaded_file.filename):
        return "Seuls les fichiers PDF sont acceptés", 400

    object_key = f"invoices/{uuid.uuid4()}-{uploaded_file.filename}"

    try:
        s3_client().upload_fileobj(
            uploaded_file,
            os.environ["S3_BUCKET"],
            object_key,
        )

        conn = db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO orders (customer, product_id, invoice_key)
                    VALUES (%s, %s, %s)
                    """,
                    (customer, product_id, object_key),
                )
            conn.commit()
        finally:
            conn.close()

        return redirect(url_for("index"))

    except (ClientError, BotoCoreError):
        app.logger.exception("Erreur Objects/S3 pendant l'upload")
        return "Le stockage du document a échoué", 502

    except Exception:
        app.logger.exception("Erreur lors de la création de la commande")
        return "La commande n'a pas pu être enregistrée", 500

@app.errorhandler(413)
def request_too_large(_error):
    return "Le fichier dépasse la taille maximale autorisée", 413

if __name__ == "__main__":
    initialize_database()
    app.run(host="0.0.0.0", port=8080)

