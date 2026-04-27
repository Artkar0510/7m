from abc import ABC, abstractmethod
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User


class OAuthProvider(ABC):
    @abstractmethod
    async def build_authorization_url(self, state: str) -> str:
        pass
    
    @abstractmethod
    async def exchange_code(self, code: str) -> str:
        pass
    
    @abstractmethod
    async def fetch_user_info(self, access_token: str) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def get_or_create_user(self, db: AsyncSession, code: str) -> User:
        pass
    
    @abstractmethod
    async def create_state(self) -> str:
        pass
    
    @abstractmethod
    async def validate_state(self, state: str) -> None:
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass