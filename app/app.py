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
  <title>NutaShop Cloud Native</title>
  <style>
    :root {
      --navy: #071b2f;
      --blue: #0b6e99;
      --cyan: #19b5c5;
      --green: #16a66a;
      --bg: #f4f7fa;
      --card: #ffffff;
      --text: #152536;
      --muted: #6b7b8c;
      --border: #e2e9ef;
      --shadow: 0 12px 32px rgba(7, 27, 47, .08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
      color: var(--text);
      background: var(--bg);
    }

    nav {
      height: 68px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 6%;
      color: white;
      background: var(--navy);
    }

    .brand {
      font-size: 22px;
      font-weight: 800;
      letter-spacing: -.5px;
    }

    .brand span { color: var(--cyan); }

    .nav-status {
      color: #b8d6df;
      font-size: 13px;
    }

    .hero {
      padding: 54px 6%;
      color: white;
      background:
        radial-gradient(circle at 80% 20%, rgba(25,181,197,.34), transparent 30%),
        linear-gradient(125deg, #071b2f, #0b6e99);
    }

    .hero h1 {
      max-width: 720px;
      margin: 0 0 12px;
      font-size: clamp(36px, 5vw, 64px);
      line-height: 1;
      letter-spacing: -2px;
    }

    .hero p {
      max-width: 680px;
      margin: 0;
      color: #d9f0f3;
      font-size: 18px;
    }

    .container {
      width: min(1180px, 88%);
      margin: 34px auto 70px;
    }

    .architecture {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
      margin-bottom: 28px;
    }

    .architecture-card,
    .panel,
    .product-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      box-shadow: var(--shadow);
    }

    .architecture-card {
      padding: 20px;
    }

    .architecture-card .label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .08em;
    }

    .architecture-card h3 {
      margin: 8px 0 4px;
    }

    .architecture-card p {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
    }

    .layout {
      display: grid;
      grid-template-columns: 1.05fr .95fr;
      gap: 24px;
      align-items: start;
    }

    .panel {
      padding: 28px;
    }

    .panel h2 {
      margin: 0 0 20px;
      font-size: 24px;
    }

    .products {
      display: grid;
      gap: 12px;
      margin-bottom: 24px;
    }

    .product-card {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 17px;
      box-shadow: none;
    }

    .product-card strong { display: block; }
    .product-card small { color: var(--muted); }

    .price {
      margin-left: 12px;
      color: var(--blue);
      font-weight: 800;
      white-space: nowrap;
    }

    label {
      display: block;
      margin: 16px 0 7px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }

    input, select {
      width: 100%;
      padding: 13px 14px;
      border: 1px solid var(--border);
      border-radius: 10px;
      font: inherit;
      background: #fbfdff;
    }

    input:focus, select:focus {
      outline: 3px solid rgba(25,181,197,.18);
      border-color: var(--cyan);
    }

    button {
      width: 100%;
      margin-top: 22px;
      padding: 14px 18px;
      border: 0;
      border-radius: 10px;
      color: white;
      background: var(--green);
      font: inherit;
      font-weight: 800;
      cursor: pointer;
    }

    button:hover { filter: brightness(.95); }

    .notice {
      margin-bottom: 18px;
      padding: 13px 15px;
      border-radius: 10px;
      background: #fff4db;
      color: #78530a;
      font-size: 14px;
    }

    .orders {
      margin-top: 24px;
    }

    .order {
      padding: 15px 0;
      border-bottom: 1px solid var(--border);
    }

    .order:last-child { border-bottom: 0; }

    .order-line {
      display: flex;
      justify-content: space-between;
      gap: 15px;
    }

    .order small {
      display: block;
      margin-top: 5px;
      color: var(--muted);
    }

    .empty {
      color: var(--muted);
      font-size: 14px;
    }

    @media (max-width: 800px) {
      .architecture,
      .layout {
        grid-template-columns: 1fr;
      }

      .container { width: 92%; }
      nav { padding: 0 4%; }
      .hero { padding: 42px 4%; }
    }
  </style>
</head>
<body>
  <nav>
    <div class="brand">Nuta<span>Shop</span></div>
    <div class="nav-status">● Application opérationnelle sur NKP</div>
  </nav>

  <header class="hero">
    <h1>Modern commerce, powered by Nutanix.</h1>
    <p>
      Une commande, une écriture PostgreSQL et un document stocké dans Objects —
      le tout exécuté sur une plateforme Kubernetes moderne.
    </p>
  </header>

  <main class="container">
    <section class="architecture">
      <div class="architecture-card">
        <div class="label">Compute</div>
        <h3>NKP</h3>
        <p>Application conteneurisée et orchestrée par Kubernetes.</p>
      </div>
      <div class="architecture-card">
        <div class="label">Database</div>
        <h3>NDB · PostgreSQL</h3>
        <p>Données transactionnelles protégées par Time Machine.</p>
      </div>
      <div class="architecture-card">
        <div class="label">Storage</div>
        <h3>Objects · S3</h3>
        <p>Factures et documents stockés dans le bucket applicatif.</p>
      </div>
    </section>

    <section class="layout">
      <div class="panel">
        <h2>Créer une commande</h2>

        <div class="products">
          {% for product in products %}
          <div class="product-card">
            <div>
              <strong>{{ product[1] }}</strong>
              <small>Service Nutanix pour applications modernes</small>
            </div>
            <div class="price">{{ "%.2f"|format(product[2]) }} €</div>
          </div>
          {% endfor %}
        </div>

        <form action="/order" method="post" enctype="multipart/form-data">
          <label for="customer">Nom du client</label>
          <input id="customer" name="customer" placeholder="Entreprise ACME" required>

          <label for="product_id">Produit</label>
          <select id="product_id" name="product_id" required>
            {% for product in products %}
            <option value="{{ product[0] }}">
              {{ product[1] }} — {{ "%.2f"|format(product[2]) }} €
            </option>
            {% endfor %}
          </select>

          <label for="file">Justificatif ou facture PDF</label>
          <input id="file" name="file" type="file" accept=".pdf,application/pdf" required>

          <button type="submit">Valider la commande</button>
        </form>
      </div>

      <div class="panel">
        <h2>Commandes récentes</h2>

        {% if orders %}
          {% for order in orders %}
          <div class="order">
            <div class="order-line">
              <strong>#{{ order[0] }} · {{ order[1] }}</strong>
              <span>{{ "%.2f"|format(order[3]) }} €</span>
            </div>
            <small>{{ order[2] }} · {{ order[5] }}</small>
            <small>Object : {{ order[4] }}</small>
          </div>
          {% endfor %}
        {% else %}
          <p class="empty">Aucune commande enregistrée.</p>
        {% endif %}

        <div class="notice">
          Démo Day-2 : la base peut être clonée depuis un point-in-time
          avec NDB Time Machine pour validation en environnement de test.
        </div>
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

