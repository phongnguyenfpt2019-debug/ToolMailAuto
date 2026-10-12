import os
from dotenv import load_dotenv

# Tự động nạp các biến môi trường từ file .env
load_dotenv()

# Database credentials are independent of the email account credentials below.
DEFAULT_SUPABASE_DB_PASSWORD = os.getenv("DEFAULT_SUPABASE_DB_PASSWORD", os.getenv("SUPABASE_DB_PASSWORD", ""))

# Default IMAP configuration for FPT Mail
DEFAULT_IMAP_SERVER = os.getenv("DEFAULT_IMAP_SERVER", "mail.fpt.net")
DEFAULT_IMAP_PORT = int(os.getenv("DEFAULT_IMAP_PORT", "993"))
DEFAULT_EMAIL = os.getenv("DEFAULT_EMAIL", "")
DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD", "")

# Database path (Hỗ trợ cả môi trường Local và Vercel Serverless /tmp)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.getenv("VERCEL"):
    DATA_DIR = os.getenv("DATA_DIR", "/tmp/data")
else:
    DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "cem_csat.db")

# Sync settings
SYNC_FOLDERS = ["INBOX", "INBOX/TP.PKT1"]
CEM_SUBJECT_PREFIX = "CEM - CSAT 1, 2 CLDV"

# Supabase (PostgreSQL) source for the CLL >3 dashboard.
SUPABASE_PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "pmhyostihrzwzwprdkbs")
SUPABASE_DB_HOST = os.getenv("SUPABASE_DB_HOST", "aws-0-ap-southeast-1.pooler.supabase.com")
SUPABASE_DB_PORT = int(os.getenv("SUPABASE_DB_PORT", "6543"))
SUPABASE_DB_NAME = os.getenv("SUPABASE_DB_NAME", "postgres")
SUPABASE_DB_USER = os.getenv("SUPABASE_DB_USER", f"postgres.{SUPABASE_PROJECT_REF}")
SUPABASE_DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD", DEFAULT_SUPABASE_DB_PASSWORD)

# Supabase mappings
SUPABASE_BT_TABLE = os.getenv("SUPABASE_BT_TABLE", "bt")
SUPABASE_BT_CONTRACT_COL = os.getenv("SUPABASE_BT_CONTRACT_COL", "Số_HĐ")
SUPABASE_BT_STAFF_COL = os.getenv("SUPABASE_BT_STAFF_COL", "Nhân_viên")
SUPABASE_BT_CREATED_COL = os.getenv("SUPABASE_BT_CREATED_COL", "TG_Tạo")
SUPABASE_BT_COMPLETED_COL = os.getenv("SUPABASE_BT_COMPLETED_COL", "dt_complete")
SUPABASE_BT_STAFF_NOTE_COL = os.getenv("SUPABASE_BT_STAFF_NOTE_COL", "Ghi_chú")
SUPABASE_BT_CC_NOTE_COL = os.getenv("SUPABASE_BT_CC_NOTE_COL", "Ghi_chú_CC")
