"""프로젝트 설정.

- Settings   : 전략 파라미터 (민감정보 아님, 깃 커밋 대상)
- Secrets    : API 키·계좌 정보 (.env에서 로드, 절대 커밋 금지)

실제 키는 프로젝트 루트의 `.env` 파일에 넣는다 (.gitignore로 제외됨).
템플릿은 `.env.example` 참고.
"""

import os
from dataclasses import dataclass
from pathlib import Path


# --------------------------------------------------------------------------
# .env 로더 (외부 의존성 없이 동작)
# --------------------------------------------------------------------------
def load_env(path: str = ".env") -> None:
    """.env 파일을 읽어 os.environ에 주입한다. 파일이 없으면 조용히 통과."""
    env_path = Path(__file__).parent / path
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # 이미 환경변수로 설정돼 있으면 그것을 우선(운영 환경 오버라이드 허용)
        os.environ.setdefault(key, value)


load_env()


# --------------------------------------------------------------------------
# 전략 파라미터 (공개)
# --------------------------------------------------------------------------
@dataclass
class Settings:
    # 지표
    short_period: int = 15
    long_period: int = 60
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_recover: float = 40.0
    # 전략 전환: True=보수적(골든크로스+RSI회복), False=추세추종(골든크로스만)
    use_rsi_filter: bool = False
    # 리스크·자금
    trailing_stop_pct: float = 0.10
    max_positions: int = 4
    position_pct: float = 0.20
    # 유니버스
    top_n: int = 100
    min_trade_value_krw: float = 1_000_000_000.0
    # 실행·저장
    db_path: str = "coin.db"
    initial_capital: float = 1_000_000.0
    fee_rate: float = 0.0004
    payment_currency: str = "KRW"


# --------------------------------------------------------------------------
# 민감정보 (.env에서 로드)
# --------------------------------------------------------------------------
@dataclass
class Secrets:
    """빗썸 API 키·계좌 정보. 값은 .env에서 주입된다."""

    bithumb_api_key: str = ""
    bithumb_secret_key: str = ""
    account_label: str = ""  # 계좌 식별용 메모 (선택)

    @classmethod
    def from_env(cls) -> "Secrets":
        return cls(
            bithumb_api_key=os.environ.get("BITHUMB_API_KEY", ""),
            bithumb_secret_key=os.environ.get("BITHUMB_SECRET_KEY", ""),
            account_label=os.environ.get("ACCOUNT_LABEL", ""),
        )

    def is_configured(self) -> bool:
        """실거래용 키가 채워졌는지 확인."""
        return bool(self.bithumb_api_key and self.bithumb_secret_key)


# --------------------------------------------------------------------------
# DB 연결 설정 (.env에서 로드)
# --------------------------------------------------------------------------
@dataclass
class Database:
    """DB 접속 정보.

    engine="mysql" 이면 로컬 MySQL, "sqlite" 이면 파일 DB를 쓴다.
    실제 봇 운영은 MySQL, 테스트는 SQLite(임시파일)를 권장한다.
    """

    engine: str = "sqlite"          # "sqlite" | "mysql"
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: str = ""
    name: str = "coin"              # 데이터베이스(스키마) 이름
    sqlite_path: str = "coin.db"    # engine="sqlite"일 때 파일 경로

    @classmethod
    def from_env(cls) -> "Database":
        return cls(
            engine=os.environ.get("DB_ENGINE", "sqlite"),
            host=os.environ.get("DB_HOST", "127.0.0.1"),
            port=int(os.environ.get("DB_PORT", "3306")),
            user=os.environ.get("DB_USER", "root"),
            password=os.environ.get("DB_PASSWORD", ""),
            name=os.environ.get("DB_NAME", "coin"),
            sqlite_path=os.environ.get("DB_SQLITE_PATH", "coin.db"),
        )

    def url(self) -> str:
        """SQLAlchemy 접속 URL을 만든다."""
        if self.engine == "mysql":
            return (
                f"mysql+pymysql://{self.user}:{self.password}"
                f"@{self.host}:{self.port}/{self.name}?charset=utf8mb4"
            )
        return f"sqlite:///{self.sqlite_path}"


settings = Settings()
secrets = Secrets.from_env()
database = Database.from_env()
