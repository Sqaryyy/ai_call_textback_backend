# create_admin_existing_session.py
import uuid
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from app.config.database import SessionLocal
from app.models.user import User, PlatformRole

# -----------------------
# Config
# -----------------------
ADMIN_EMAIL = "lukapilip@gmail.com"
ADMIN_PASSWORD = "PipiPipi1"
ADMIN_FULL_NAME = "Luka Pilip"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# -----------------------
# Main
# -----------------------
db: Session = SessionLocal()

try:
    existing_admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if existing_admin:
        print(f"Admin user already exists: {ADMIN_EMAIL}")
    else:
        admin = User(
            email=ADMIN_EMAIL,
            hashed_password=hash_password(ADMIN_PASSWORD),
            full_name=ADMIN_FULL_NAME,
            role=PlatformRole.ADMIN,
            is_active=True,
            is_verified=True
        )
        db.add(admin)
        db.commit()
        print(f"✅ Admin user created: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
finally:
    db.close()
