"""
Точка входа для ручной подачи идеи в общий бэклог (см.
workflows/product_backlog.py::_main(), context/idea_to_ecosystem_pipeline.md
Промт 1, пункт 2). НЕ для директив на немедленное исполнение — для
этого /goal (main_goal.py).

Запуск:
    python main_submit_idea.py "заголовок" "описание" крупное
    python main_submit_idea.py "заголовок" "описание"           # мелкое по умолчанию
"""

from dotenv import load_dotenv

load_dotenv()

from workflows.product_backlog import _main

if __name__ == "__main__":
    _main()
