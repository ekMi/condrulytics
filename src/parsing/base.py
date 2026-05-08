from abc import ABC, abstractmethod
from pathlib import Path
import pandas as pd

class ParserStrategy(ABC):

    @staticmethod
    @abstractmethod
    def can_handle(full_text: str) -> bool:
        pass

    @abstractmethod
    def parse(self, pdf_path: str | Path) -> tuple[pd.DataFrame, dict]:
        """
        Retourne :
        - DataFrame
        - metadata dict (ex: {"expected_count": 123})
        """
        pass