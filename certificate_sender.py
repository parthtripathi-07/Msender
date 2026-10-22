"""
Certificate Generator + Auto Mailer
-----------------------------------
participants.csv  ->  (name, email)
Har bande ke naam se alag PDF banta hai aur usi ke email par jata hai.

Use:
  python certificate_sender.py generate        # sirf PDFs banao (certificates/ folder me)
  python certificate_sender.py test            # sab mails sirf APNE email par bhejo (check karne ke liye)
  python certificate_sender.py send            # asli me sabko bhejo
"""
import csv, io, os, re, smtplib, sys, getpass, time
from email.message import EmailMessage
from email.utils import formataddr
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.colors import HexColor
from pypdf import PdfReader, PdfWriter

# Windows terminal UTF-8 encoding fix (prevents UnicodeEncodeError with emojis)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ================== YAHAN APNI DETAILS BADLO ==================
EVENT_NAME   = "spectrum edge"
COLLEGE_NAME = "KIPM college"
SENDER_EMAIL = "avinashtripathi643@gmail.com"      # jis gmail se bhejna hai
CSV_FILE     = "participants.csv"
OUTPUT_DIR   = "certificates"
SENT_LOG     = "sent_log.txt"            # jinko mail chali gayi unka record (dobara nahi jayegi)

# Agar tumhara khud ka certificate design (PDF) hai, to uska naam likho. Warna None rehne do.
TEMPLATE_PDF = None                      # e.g. "template.pdf"

# Agar sabko EK HI common PDF bhejna hai (bina naam customize kiye, e.g. brochure/notice), uska path likho:
COMMON_PDF   =  None                     # e.g. "brochure.pdf" (warna None rehne do)
# Template me naam kahan likhna hai (points me; (0,0) neeche-left hai)
NAME_Y       = 300                       # upar-niche karne ke liye ye badlo
NAME_FONT    = "Helvetica-Bold"
NAME_SIZE    = 36
NAME_COLOR   = "#1a237e"

SUBJECT = f"Your Participation Certificate - {EVENT_NAME}"
BODY = """Dear {name},

Thank you for participating in {event}. Please find your participation certificate attached.

Best regards,
{college}
"""
# ===============================================================


def make_certificate(name: str, path: str):
    """Naam wala certificate PDF banao."""
    if TEMPLATE_PDF:
        if not os.path.exists(TEMPLATE_PDF):
            print(f"❌ Error: Template PDF '{TEMPLATE_PDF}' nahi mila!")
            sys.exit(1)
        base = PdfReader(TEMPLATE_PDF).pages[0]
        w, h = float(base.mediabox.width), float(base.mediabox.height)
    else:
        w, h = landscape(A4)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))

    if not TEMPLATE_PDF:  # default simple design
        c.setStrokeColor(HexColor("#1a237e")); c.setLineWidth(6)
        c.rect(25, 25, w - 50, h - 50)
        c.setLineWidth(1.5); c.rect(38, 38, w - 76, h - 76)
        c.setFillColor(HexColor("#1a237e")); c.setFont("Helvetica-Bold", 40)
        c.drawCentredString(w / 2, h - 120, "CERTIFICATE")
        c.setFont("Helvetica", 18)
        c.drawCentredString(w / 2, h - 150, "OF PARTICIPATION")
        c.setFillColor(HexColor("#333333")); c.setFont("Helvetica", 16)
        c.drawCentredString(w / 2, h - 210, "This is proudly presented to")
        c.setFont("Helvetica", 16)
        c.drawCentredString(w / 2, 260, f"for participating in {EVENT_NAME}")
        c.drawCentredString(w / 2, 235, f"organised by {COLLEGE_NAME}")
        y = h - 280
    else:
        y = NAME_Y

    # Display name formatting (e.g. 'avinash' -> 'Avinash') agar sab lowercase ho
    display_name = name.title() if name.islower() else name

    # naam (lamba naam ho to font chhota ho jayega)
    size = NAME_SIZE
    while c.stringWidth(display_name, NAME_FONT, size) > w - 150 and size > 14:
        size -= 1
    c.setFillColor(HexColor(NAME_COLOR)); c.setFont(NAME_FONT, size)
    c.drawCentredString(w / 2, y, display_name)
    c.save(); buf.seek(0)

    if TEMPLATE_PDF:
        base.merge_page(PdfReader(buf).pages[0])
        page = base
    else:
        page = PdfReader(buf).pages[0]
    writer = PdfWriter(); writer.add_page(page)
    with open(path, "wb") as f:
        writer.write(f)


def safe_filename(name):
    clean = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE)
    return clean.strip("_") or "certificate"


def read_participants():
    if not os.path.exists(CSV_FILE):
        print(f"❌ Error: '{CSV_FILE}' file nahi mili!")
        sys.exit(1)
    rows, seen = [], set()
    with open(CSV_FILE, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if not r:
                continue
            # Header ko case-insensitive aur whitespace-free banayein
            clean_row = {str(k).strip().lower(): str(v).strip() if v else "" for k, v in r.items() if k}
            name = clean_row.get("name", "").strip()
            email = clean_row.get("email", "").strip().lower()
            if not name or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                print(f"⚠️  Skip (galat name/email): {name!r} {email!r}")
                continue
            if email in seen:
                print(f"⚠️  Skip (duplicate email): {email}")
                continue
            seen.add(email)
            rows.append((name, email))
    return rows


def already_sent():
    if not os.path.exists(SENT_LOG):
        return set()
    return {l.strip() for l in open(SENT_LOG, encoding="utf-8") if l.strip()}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "generate"
    if mode not in ("generate", "test", "send"):
        sys.exit(__doc__)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    people = read_participants()
    print(f"Total participants: {len(people)}")

    server = None
    if mode in ("test", "send"):
        pwd = os.environ.get("GMAIL_APP_PASSWORD") or getpass.getpass("Gmail App Password: ")
        clean_pwd = pwd.replace(" ", "").strip()
        if not clean_pwd:
            print("\n❌ Error: Password khali (empty) tha! Kripya valid 16-letter App Password daalein.\n")
            sys.exit(1)
        try:
            print("Connecting to Gmail SMTP...")
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
            server.starttls()
            server.login(SENDER_EMAIL, clean_pwd)
            print("✅ Gmail SMTP login successful!\n")
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPServerDisconnected):
            print("\n❌ Gmail Login Failed: Username ya Password reject ho gaya!")
            print("----------------------------------------------------------------")
            print("Gmail ne connection close kar diya (Bad Credentials).")
            print("👉 Iska matlab: Aapka Gmail Password ya App Password GALAT / REJECT hua hai.")
            print("")
            print("👉 IMPORTANT: Gmail me normal account password kaam NAHI karega.")
            print("👉 Aapko Google Account me 'App Password' generate karna padega:")
            print("   1. Apne Google Account me '2-Step Verification' ON karein:")
            print("      https://myaccount.google.com/signinoptions/two-step-verification")
            print("   2. Fir 'App Passwords' page open karein:")
            print("      https://myaccount.google.com/apppasswords")
            print("   3. Ek App name daalein (jaise 'Msender') aur 'Create' par click karein.")
            print("   4. Jo 16-letter ka password milega (e.g. 'abcd efgh ijkl mnop'), use copy karein.")
            print("   Note: Password type karte waqt screen par dikhai nahi dega, bas paste karke Enter daba dein.")
            print("----------------------------------------------------------------\n")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ SMTP Connection Error: {e}\n")
            sys.exit(1)
    sent = already_sent() if mode == "send" else set()

    for i, (name, email) in enumerate(people, 1):
        if email in sent:
            print(f"[{i}] ⏭️  Pehle bhej chuka: {name}"); continue
        if COMMON_PDF:
            if not os.path.exists(COMMON_PDF):
                print(f"❌ Error: Common PDF file '{COMMON_PDF}' nahi mili!")
                sys.exit(1)
            pdf_path = COMMON_PDF
            if mode == "generate":
                print(f"[{i}] ℹ️ Common PDF Ready ({COMMON_PDF}) for: {name}"); continue
        else:
            pdf_path = os.path.join(OUTPUT_DIR, f"{safe_filename(name)}_Certificate.pdf")
            make_certificate(name, pdf_path)
            if mode == "generate":
                print(f"[{i}] ✅ PDF bana: {name}"); continue

        to = SENDER_EMAIL if mode == "test" else email   # test me khud ko hi jayega
        msg = EmailMessage()
        msg["From"] = formataddr((COLLEGE_NAME, SENDER_EMAIL))
        msg["To"] = to
        msg["Subject"] = SUBJECT
        msg.set_content(BODY.format(name=name, event=EVENT_NAME, college=COLLEGE_NAME))
        with open(pdf_path, "rb") as f:
            msg.add_attachment(f.read(), maintype="application", subtype="pdf",
                               filename=os.path.basename(pdf_path))
        try:
            server.send_message(msg)
            print(f"[{i}] 📧 Sent: {name} -> {to}")
            if mode == "send":
                open(SENT_LOG, "a", encoding="utf-8").write(email + "\n")
            time.sleep(2)   # Gmail ki limit se bachne ke liye
        except Exception as e:
            print(f"[{i}] ❌ Fail: {name} ({email}) - {e}")
    if server:
        server.quit()


if __name__ == "__main__":
    main()