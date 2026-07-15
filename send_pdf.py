import os
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

import gspread
from google.oauth2.service_account import Credentials

# ─── Config ───
SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
SMTP_HOST = "mail.smtp2go.com"
SMTP_PORT = 587
SMTP_USER = os.environ["SMTP2GO_USER"]
SMTP_PASS = os.environ["SMTP2GO_PASS"]
PDF_FILE = "material-medalii.pdf"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_col_indexes(headers):
    try:
        return {
            "pdf": headers.index("PDF_Trimis") + 1,
            "incercari": headers.index("Incercari") + 1,
        }
    except ValueError as e:
        raise Exception(f"Lipseste o coloana obligatorie din header: {e}")

def trimite_email(to_email: str):
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = "Materialul tau despre medaliile de aur de pe eticheta vinului"

    body = """Salut,

Asa cum am promis, uite materialul detaliat despre ce garanteaza (si ce nu) o medalie de aur pe eticheta unei sticle de vin.

Daca vrei sa primesti si alte povesti din lumea vinului, poti sa te abonezi aici:
https://www.vinuldemiercuri.ro/info/abonare-email

Daca ai intrebari sau vrei sa povestim mai mult, imi scrii oricand inapoi.

Toate cele bune,
Lucian
"""
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with open(PDF_FILE, "rb") as f:
        atasament = MIMEApplication(f.read(), _subtype="pdf")
        atasament.add_header(
            "Content-Disposition", "attachment", filename="medalii-de-aur-vin.pdf"
        )
        msg.attach(atasament)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, msg.as_string())

def main():
    creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).worksheet("Sheet1")

    records = sheet.get_all_records()
    headers = sheet.row_values(1)
    cols = get_col_indexes(headers)

    # ─── ANTI-DUPLICAT: colectam toate emailurile deja trimise sau invalidate ───
    processed_emails = set()
    for row in records:
        e = str(row.get("Email", "")).strip().lower()
        t = str(row.get("PDF_Trimis", "")).strip()
        if e and (t == "Da" or t == "Invalid"):
            processed_emails.add(e)

    for idx, row in enumerate(records, start=2):
        email = str(row.get("Email", "")).strip()
        email_lower = email.lower()
        trimis = str(row.get("PDF_Trimis", "")).strip()

        # Skip gol sau deja marcat pe acest rand
        if not email or trimis == "Da" or trimis == "Invalid":
            continue

        # ─── ANTI-DUPLICAT: daca emailul a fost deja trimis/invalidat in alt rand, sarim ───
        if email_lower in processed_emails:
            print(f"{email} -> Duplicat (deja trimis sau invalid in alta inregistrare), marchez Da")
            sheet.update_cell(idx, cols["pdf"], "Da")
            continue

        # Citeste numarul de incercari (gol = 0)
        inc_raw = row.get("Incercari", "")
        incercari = int(inc_raw) if str(inc_raw).strip() else 0

        # Safety: daca incercarile au ajuns deja la 2 dar nu e marcat Invalid
        if incercari >= 2:
            if trimis != "Invalid":
                sheet.update_cell(idx, cols["pdf"], "Invalid")
                processed_emails.add(email_lower)
                print(f"{email} -> Invalid (deja 2 incercari esuate)")
            continue

        # ─── Trimite emailul ───
        try:
            print(f"Trimit catre {email} ... (incercarea {incercari + 1})")
            trimite_email(email)

            # Succes: marcheaza Da, sterge incercarile, adauga in setul anti-duplicat
            sheet.update_cell(idx, cols["pdf"], "Da")
            sheet.update_cell(idx, cols["incercari"], "")
            processed_emails.add(email_lower)
            print(f"{email} -> Trimis cu succes")

            time.sleep(2)

        except Exception as e:
            print(f"Eroare la {email}: {e}")
            incercari += 1
            sheet.update_cell(idx, cols["incercari"], incercari)

            # Esec la a 2-a incercare -> scoate din flux permanent
            if incercari >= 2:
                sheet.update_cell(idx, cols["pdf"], "Invalid")
                processed_emails.add(email_lower)
                print(f"{email} -> Invalid (2 esecuri, scos din flux)")
            else:
                print(f"{email} -> Retry programat (incercarea {incercari})")

            time.sleep(2)

if __name__ == "__main__":
    main()
