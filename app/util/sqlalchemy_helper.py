import logging
from sqlalchemy import create_engine, Column, Integer, String, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import Iterable


Base = declarative_base()


class BotUser(Base):
    __tablename__ = 'bot_users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    chat_id = Column(String(128), nullable=False)
    __table_args__ = (
        UniqueConstraint('name', 'chat_id', name='unique_name_chat_id'), 
    )


class SqlalchemyHelper():
    
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        self.session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        
    def add_bot_user(self, obj: BotUser) -> bool:
        session = self.session()
        try:
            session.add(obj)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logging.error(f"Failed to add BotUser: {e}")
            return False
        finally:
            session.close()
    
    def get_all_bot_user(self) -> Iterable[BotUser]:
        session = self.session()
        try:
            return session.query(BotUser).all()
        except Exception as e:
            logging.error(f"Failed to retrieve BotUsers: {e}")
            return []
        finally:
            session.close()