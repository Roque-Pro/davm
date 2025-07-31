# app.py — backend completo (Flask + Pandas + Plotly + Exportações)

from pathlib import Path
import io
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from flask import Flask, render_template, request, Response
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader



import os, plotly.io as pio
os.environ["KALEIDO_BROWSER_PATH"] = r"C:\Users\roque\AppData\Local\choreographer\chrome-win64\chrome.exe"  # <-- use o caminho que apareceu no seu PC

# flags que ajudam no Windows/headless
try:
    pio.kaleido.scope.chromium_args += [
        "--headless=new", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
    ]
except Exception:
    pass


# -----------------------------------------------------------
# Caminhos do projeto
# -----------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# -----------------------------------------------------------
# Flask app (com caminhos explícitos e cache reduzido em dev)
# -----------------------------------------------------------
app = Flask(
    __name__,
    static_folder=str(BASE_DIR / "static"),
    template_folder=str(BASE_DIR / "templates"),
    static_url_path="/static",
)
app.config.update(
    TEMPLATES_AUTO_RELOAD=True,
    SEND_FILE_MAX_AGE_DEFAULT=0,  # evita cache de estáticos em dev
)

# -----------------------------------------------------------
# Utilidades de formatação
# -----------------------------------------------------------
def fmt_currency_br(v: float) -> str:
    try:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def fmt_number(v: int) -> str:
    try:
        return f"{v:,}".replace(",", ".")
    except Exception:
        return "0"

# -----------------------------------------------------------
# ETL — leitura dos CSVs e base unificada (apenas pedidos entregues)
# -----------------------------------------------------------
def load_base_delivered(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    data_dir = Path(data_dir)

    def _read_csv(name, parse_dates=None):
        path = data_dir / name
        return pd.read_csv(
            path,
            parse_dates=parse_dates,
            encoding="utf-8",
            sep=",",
            low_memory=False
        )

    # Tabelas essenciais
    orders = _read_csv(
        "olist_orders_dataset.csv",
        parse_dates=[
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
    )
    items = _read_csv("olist_order_items_dataset.csv")
    payments = _read_csv("olist_order_payments_dataset.csv")
    products = _read_csv("olist_products_dataset.csv")
    customers = _read_csv("olist_customers_dataset.csv")

    # Receita por pedido
    pay_by_order = (
        payments.groupby("order_id", as_index=False)["payment_value"]
        .sum()
        .rename(columns={"payment_value": "order_revenue"})
    )

    # Base: orders + receita + UF do cliente
    df = orders.merge(pay_by_order, on="order_id", how="left")
    df = df.merge(
        customers[["customer_id", "customer_state"]],
        on="customer_id",
        how="left",
    )

    # Categoria principal do pedido (moda das categorias dos itens)
    items_prod = items.merge(
        products[["product_id", "product_category_name"]],
        on="product_id",
        how="left",
    )
    cat_by_order = (
        items_prod.groupby("order_id")["product_category_name"]
        .agg(lambda s: s.mode().iat[0] if not s.mode().empty else None)
        .reset_index()
        .rename(columns={"product_category_name": "main_category"})
    )
    df = df.merge(cat_by_order, on="order_id", how="left")

    # Apenas pedidos entregues
    delivered = df[df["order_status"] == "delivered"].copy()

    # Métricas auxiliares
    delivered["delivery_days"] = (
        delivered["order_delivered_customer_date"]
        - delivered["order_purchase_timestamp"]
    ).dt.days
    delivered["delivered_on_time"] = (
        delivered["order_delivered_customer_date"]
        <= delivered["order_estimated_delivery_date"]
    )

    # Base mínima para análises/telas
    delivered = delivered[[
        "order_id",
        "order_purchase_timestamp",
        "order_revenue",
        "main_category",
        "customer_state",
        "delivery_days",
        "delivered_on_time",
    ]].copy()

    delivered["order_revenue"] = delivered["order_revenue"].fillna(0.0)
    delivered = delivered.dropna(subset=["order_purchase_timestamp"])
    return delivered

# Carrega base ao subir o servidor
BASE = load_base_delivered(DATA_DIR)

# -----------------------------------------------------------
# Helpers de filtro e de construção de figuras
# -----------------------------------------------------------
def filter_df_by_dates(base_df: pd.DataFrame, start_str: str | None, end_str: str | None):
    """Filtra BASE pelo intervalo [start, end]. Retorna (df, start_dt, end_dt, min_dt, max_dt)."""
    min_dt = pd.to_datetime(base_df["order_purchase_timestamp"].min()).date()
    max_dt = pd.to_datetime(base_df["order_purchase_timestamp"].max()).date()

    start_dt = pd.to_datetime(start_str).date() if start_str else min_dt
    end_dt = pd.to_datetime(end_str).date() if end_str else max_dt
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    mask = (base_df["order_purchase_timestamp"].dt.date >= start_dt) & \
           (base_df["order_purchase_timestamp"].dt.date <= end_dt)
    df = base_df.loc[mask].copy()
    return df, start_dt, end_dt, min_dt, max_dt

def build_figures(df: pd.DataFrame):
    """Gera as 3 figuras do dashboard a partir de um DF filtrado."""
    # Receita mensal
    if not df.empty:
        m = df.copy()
        m["purchase_month"] = m["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp()
        monthly = (
            m.groupby("purchase_month")
             .agg(revenue=("order_revenue","sum"), orders=("order_id","nunique"))
             .reset_index()
             .sort_values("purchase_month")
        )
    else:
        monthly = pd.DataFrame({"purchase_month": [], "revenue": [], "orders": []})

    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=monthly["purchase_month"], y=monthly["revenue"],
        mode="lines+markers", name="Receita"
    ))
    fig1.update_layout(
        margin=dict(l=20, r=20, t=40, b=20),
        height=380, template="plotly_dark",
        title="Receita Mensal",
    )

    # Top 10 categorias
    cat = (df.groupby("main_category")["order_revenue"]
           .sum().sort_values(ascending=False).head(10).reset_index()
           .rename(columns={"order_revenue":"revenue"})) if not df.empty \
           else pd.DataFrame({"main_category": [], "revenue": []})
    fig2 = go.Figure(go.Bar(x=cat["main_category"], y=cat["revenue"], name="Receita"))
    fig2.update_layout(
        margin=dict(l=20, r=20, t=40, b=60),
        height=380, template="plotly_dark",
        title="Top 10 Categorias (Receita)", xaxis_tickangle=-30,
    )

    # Pedidos por UF
    uf = (df.groupby("customer_state")["order_id"].nunique()
          .sort_values(ascending=False).reset_index()
          .rename(columns={"order_id":"orders"})) if not df.empty \
          else pd.DataFrame({"customer_state": [], "orders": []})
    fig3 = go.Figure(go.Bar(x=uf["customer_state"], y=uf["orders"], name="Pedidos"))
    fig3.update_layout(
        margin=dict(l=20, r=20, t=40, b=40),
        height=380, template="plotly_dark",
        title="Pedidos por UF",
    )

    return fig1, fig2, fig3

# -----------------------------------------------------------
# Rotas
# -----------------------------------------------------------
@app.route("/")
def index():
    # Filtros de data vindos da query string
    start_str = request.args.get("start")
    end_str   = request.args.get("end")

    df, start_dt, end_dt, min_dt, max_dt = filter_df_by_dates(BASE, start_str, end_str)

    # KPIs
    total_revenue = float(df["order_revenue"].sum()) if not df.empty else 0.0
    total_orders = int(df["order_id"].nunique()) if not df.empty else 0
    avg_ticket = float(total_revenue / total_orders) if total_orders else 0.0
    avg_delivery_days = float(df["delivery_days"].dropna().mean()) if not df.empty else 0.0
    pct_on_time = float(df["delivered_on_time"].mean() * 100.0) if not df.empty else 0.0

    kpi = {
        "revenue": fmt_currency_br(total_revenue),
        "orders": fmt_number(total_orders),
        "avg_ticket": fmt_currency_br(avg_ticket),
    }
    extras = {
        "avg_delivery_days": round(avg_delivery_days, 1),
        "pct_on_time": round(pct_on_time, 1),
    }

    # Figuras
    fig1, fig2, fig3 = build_figures(df)

    return render_template(
        "index.html",
        page_title="Dashboard de Vendas e Marketing",
        graph1JSON=fig1.to_json(),
        graph2JSON=fig2.to_json(),
        graph3JSON=fig3.to_json(),
        kpi=kpi,
        extras=extras,
        min_dt=min_dt.isoformat(),
        max_dt=max_dt.isoformat(),
        start_dt=start_dt.isoformat(),
        end_dt=end_dt.isoformat(),
    )

# --- Exportação CSV (endpoint = 'export' para combinar com o template) ---
@app.route("/export", methods=["GET"], endpoint="export")
def export_csv():
    start_str = request.args.get("start")
    end_str   = request.args.get("end")

    df, start_dt, end_dt, _, _ = filter_df_by_dates(BASE, start_str, end_str)

    buf = io.StringIO()
    df.to_csv(buf, index=False, sep=";")
    buf.seek(0)

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=rel_csv_data.csv"}
    )

# --- Exportação PDF com os 3 gráficos ---
@app.route("/export_pdf", methods=["GET"])
def export_pdf():
    start_str = request.args.get("start")
    end_str   = request.args.get("end")

    df, start_dt, end_dt, _, _ = filter_df_by_dates(BASE, start_str, end_str)
    fig1, fig2, fig3 = build_figures(df)

    # Renderiza figuras para PNG (requer kaleido)
    images = []
    for fig in (fig1, fig2, fig3):
        png_bytes = pio.to_image(fig, format="png", scale=2)
        images.append(png_bytes)

    # Monta um PDF A4 (uma página por gráfico) com título
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    width, height = A4
    margin = 36
    max_w = width - 2 * margin
    max_h = height - 2 * margin - 40

    title = f"Relatório de Vendas — {start_dt} a {end_dt}"

    for i, png in enumerate(images, start=1):
        if i > 1:
            c.showPage()
        c.setFont("Helvetica-Bold", 14)
        c.drawString(margin, height - margin, title)

        img = ImageReader(io.BytesIO(png))
        iw, ih = img.getSize()
        scale = min(max_w / iw, max_h / ih)
        w, h = iw * scale, ih * scale
        x = margin + (max_w - w) / 2
        y = margin + (max_h - h) / 2
        c.drawImage(img, x, y, width=w, height=h)

    c.save()
    pdf_buffer.seek(0)

    return Response(
        pdf_buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=rel_pdf_data.pdf"}
    )

# -----------------------------------------------------------
# Main
# -----------------------------------------------------------
if __name__ == "__main__":
    # Rode com:  py app.py
    print("STATIC FOLDER:", app.static_folder)
    print("TEMPLATE FOLDER:", app.template_folder)
    app.run(debug=True)
