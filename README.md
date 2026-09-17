# Digital Classroom Quiz Application

Flask-based quiz platform for a college assignment.

## Features
- Teacher login (default local password: `teacher123`; it is not displayed on the login page)
- Teacher can create, edit and delete quizzes
- Teacher can add, edit and delete questions
- Students enter name and register number before starting
- Attendance records start date/time
- 45 seconds per question with browser countdown and server-side timing validation
- Multiple attempts per student
- Teacher dashboard shows only the latest attempt for each register number per quiz
- Student sees score and question-by-question wrong-answer review
- Previous attempt answers are stored as snapshots so later question edits do not change old result reviews
- SQLite locally; set `DATABASE_URL` for a persistent cloud database

## Run in VS Code
```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## Important
If this is a fresh version, do not copy an old `quiz.db` into the folder. The database schema includes new fields for question snapshots and active/deleted questions.

For cloud deployment, set `TEACHER_PASSWORD` and `SECRET_KEY` as environment variables instead of relying on defaults.
