import sys
sys.path.insert(0, '.')
from database.connection import db
db.get_connection()

# Check constraints on usuarios table
rows = db.fetch_all(
    "SELECT conname, contype, pg_get_constraintdef(oid) as defn "
    "FROM pg_constraint "
    "WHERE conrelid = (SELECT oid FROM pg_class WHERE relname = 'usuarios')"
)
print("=== Constraints on usuarios ===")
for r in rows:
    print(f"  {r['conname']}: {r['defn']}")

# Check columns of usuarios
cols = db.fetch_all(
    "SELECT column_name, data_type, is_nullable, column_default "
    "FROM information_schema.columns "
    "WHERE table_name = 'usuarios' ORDER BY ordinal_position"
)
print("\n=== Columns on usuarios ===")
for c in cols:
    print(f"  {c['column_name']}: {c['data_type']} nullable={c['is_nullable']} default={c['column_default']}")
