Распаковать поверх корня репозитория bld-team (пути внутри архива уже
соответствуют структуре репо — workflows/, tools/, .github/workflows/).

НОВЫЕ файлы (просто появятся):
- workflows/product_backlog.py
- workflows/domain_scan.py
- main_domain_scan.py
- .github/workflows/domain_scan.yml

ИЗМЕНЁННЫЕ файлы (перезапишут существующие целиком):
- tools/telegram_report.py
- workflows/_common.py
- workflows/individual_initiative.py
- workflows/engineering_task.py
- workflows/company_pulse.py
- workflows/executive_meeting.py
- workflows/breakthrough_proposal.py
- workflows/big_projects.py
- workflows/hr_checkin.py
- workflows/task_board.py
- workflows/board_meeting.py
- workflows/goal_intake.py
- workflows/lab_session.py
- workflows/gtm_initiative.py
- workflows/chevruta.py
- workflows/office_chat.py
- workflows/squad_initiative.py

Не тронуты (осознанно, не меняй): hr_rotation_review.py, goal_status.py,
mentorship.py — уже были минимальны, не источник шума.

Весь набор прогнан через `python3 -m py_compile` без ошибок.
