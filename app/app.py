import os
import uuid

import boto3
import psycopg2
from botocore.config import Config
from flask import Flask, redirect, render_template_string, request, url_for

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    price_cents INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer TEXT NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id),
    invoice_key TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO products (name, price_cents) VALUES
    ('Nutanix Enterprise Cloud Platform', 999900),
    ('Nutanix Kubernetes Platform', 499900)
ON CONFLICT (name) DO NOTHING;
"""

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>NutaShop</title>
  <style>
    body { font-family: Arial; margin: 30px; background: #f3f5f7; }
    .header { background: #075985; color: white; padding: 18px; border-radius: 8px; }
    .card { background: white; padding: 18px; margin-top: 18px; border-radius: 8px; }
    input, select, button { padding: 9px; margin: 5px 0; }
    button { background: #16a34a; color: white; border: 0; border-radius: 4px; }
  </style>
</head>
<body>
  <div class="header">
    <h1>NutaShop</h1>
    <p>NKP | NDB PostgreSQL | Nutanix Objects S3</p>
  </div>

  <div class="card">
    <h2>Nouvelle commande</h2>
    <form action="/order" method="post" enctype="multipart/form-data">
      <input name="customer" placeholder="Nom du client" required>
      <br>
      <select name="product_id" required>
        {% for product in products %}
          <option value="{{ product[0] }}">
            {{ product[1] }} — {{ "%.2f"|format(product[2] / 100) }} €
          </option>
        {% endfor %}
      </select>
      <br>
      <input type="file" name="file" accept="application/pdf" required>
      <br>
      <button type="submit">Valider la commande</button>
    </form>
  </div>

  <div class="card">
    <h2>Commandes enregistrées dans PostgreSQL</h2>
    <ul>
      {% for order in orders %}
        <li>
          #{{ order[0] }} — {{ order[1] }} — {{ order[2] }} —
          <a href="{{ url_for('invoice', order_id=order[0]) }}">Facture Objects</a>
        </li>
      {% else %}
        <li>Aucune commande.</li>
      {% endfor %}
    </ul>
  </div>
</body>
</html>
"""


def db_connection():
    return psycopg2.connect(
        host=os.environ["PG_HOST"],
        port=os.getenv("PG_PORT", "5432"),
        dbname=os.environ["PG_DB"],
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASS"],
    )


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        verify=False,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def initialize_database():
    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, price_cents FROM products ORDER BY id")
            products = cur.fetchall()
            cur.execute(
                """SELECT o.id, o.customer, p.name
                   FROM orders o
                   JOIN products p ON p.id = o.product_id
                   ORDER BY o.id DESC"""
            )
            orders = cur.fetchall()
        return render_template_string(HTML, products=products, orders=orders)
    finally:
        conn.close()


@app.post("/order")
def create_order():
    customer = request.form["customer"]
    product_id = request.form["product_id"]
    uploaded_file = request.files["file"]

    if uploaded_file.mimetype != "application/pdf":
        return "Veuillez fournir un fichier PDF", 400

    # La clé est générée par l’application, pas par le nom du fichier utilisateur.
    invoice_key = f"invoices/{uuid.uuid4().hex}.pdf"

    s3_client().upload_fileobj(
        uploaded_file,
        os.environ["S3_BUCKET"],
        invoice_key,
        ExtraArgs={"ContentType": "application/pdf"},
    )

    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO orders(customer, product_id, invoice_key)
                   VALUES (%s, %s, %s)""",
                (customer, product_id, invoice_key),
            )
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("index"))


@app.get("/invoice/<int:order_id>")
def invoice(order_id):
    conn = db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT invoice_key FROM orders WHERE id = %s",
                (order_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return "Facture introuvable", 404

    signed_url = s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": os.environ["S3_BUCKET"], "Key": row[0]},
        ExpiresIn=300,
    )
    return redirect(signed_url)


initialize_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)


