from datetime import datetime, timezone
from functools import wraps
import os
import time

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")

database_url = os.environ.get("DATABASE_URL", "sqlite:///quiz.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

QUESTION_TIME_LIMIT = 45
DEFAULT_TEACHER_PASSWORD = os.environ.get("TEACHER_PASSWORD", "teacher123")


class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    questions = db.relationship(
        "Question", backref="quiz", cascade="all, delete-orphan",
        order_by="Question.id"
    )
    attempts = db.relationship(
        "Attempt", backref="quiz", cascade="all, delete-orphan"
    )


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=False)
    question = db.Column(db.String(500), nullable=False)
    option1 = db.Column(db.String(250), nullable=False)
    option2 = db.Column(db.String(250), nullable=False)
    option3 = db.Column(db.String(250), nullable=False)
    option4 = db.Column(db.String(250), nullable=False)
    correct_answer = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quiz.id"), nullable=False)
    student_name = db.Column(db.String(150), nullable=False)
    register_no = db.Column(db.String(80), nullable=False, index=True)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)
    score = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="in_progress")

    answers = db.relationship(
        "AttemptAnswer", backref="attempt", cascade="all, delete-orphan",
        order_by="AttemptAnswer.question_id"
    )


class AttemptAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("attempt.id"), nullable=False)
    question_id = db.Column(db.Integer, nullable=False)
    question_text = db.Column(db.String(500), nullable=False)
    option1 = db.Column(db.String(250), nullable=False)
    option2 = db.Column(db.String(250), nullable=False)
    option3 = db.Column(db.String(250), nullable=False)
    option4 = db.Column(db.String(250), nullable=False)
    correct_answer = db.Column(db.String(20), nullable=False)
    selected_answer = db.Column(db.String(20), nullable=True)
    is_correct = db.Column(db.Boolean, default=False)
    timed_out = db.Column(db.Boolean, default=False)


def teacher_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("teacher_authenticated"):
            return redirect(url_for("teacher_login"))
        return view(*args, **kwargs)
    return wrapped


def option_text_from_answer(answer, key):
    if not key:
        return "Not answered"
    return {
        "option1": answer.option1,
        "option2": answer.option2,
        "option3": answer.option3,
        "option4": answer.option4,
    }.get(key, "Not answered")


def latest_attempts_by_student(attempts):
    """Return exactly one latest attempt per register number for a quiz."""
    latest = {}
    for attempt in sorted(
        attempts,
        key=lambda a: (a.started_at or datetime.min.replace(tzinfo=timezone.utc), a.id),
        reverse=True,
    ):
        key = attempt.register_no.strip().upper()
        if key not in latest:
            latest[key] = attempt
    return list(latest.values())


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/teacher/login", methods=["GET", "POST"])
def teacher_login():
    if session.get("teacher_authenticated"):
        return redirect(url_for("teacher"))

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == DEFAULT_TEACHER_PASSWORD:
            session["teacher_authenticated"] = True
            return redirect(url_for("teacher"))
        flash("Incorrect teacher password.", "danger")

    return render_template("teacher_login.html")


@app.route("/teacher/logout")
def teacher_logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/teacher")
@teacher_required
def teacher():
    quizzes = Quiz.query.order_by(Quiz.id.desc()).all()
    attendance = []
    for quiz in quizzes:
        latest = latest_attempts_by_student(
            Attempt.query.filter_by(quiz_id=quiz.id)
            .order_by(Attempt.started_at.desc(), Attempt.id.desc())
            .all()
        )
        for attempt in latest:
            attendance.append({"quiz": quiz, "attempt": attempt})
    return render_template("teacher.html", quizzes=quizzes, attendance=attendance)


@app.route("/create_quiz", methods=["GET", "POST"])
@teacher_required
def create_quiz():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Quiz title is required.", "danger")
            return redirect(url_for("create_quiz"))
        quiz = Quiz(title=title)
        db.session.add(quiz)
        db.session.commit()
        flash("Quiz created. Add questions now, or return to the dashboard when finished.", "success")
        return redirect(url_for("add_question", quiz_id=quiz.id))
    return render_template("create_quiz.html")


@app.route("/edit_quiz/<int:quiz_id>", methods=["GET", "POST"])
@teacher_required
def edit_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Quiz title is required.", "danger")
            return redirect(url_for("edit_quiz", quiz_id=quiz.id))
        quiz.title = title
        db.session.commit()
        flash("Quiz title updated.", "success")
        return redirect(url_for("teacher"))
    return render_template("edit_quiz.html", quiz=quiz)


@app.post("/delete_quiz/<int:quiz_id>")
@teacher_required
def delete_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    title = quiz.title
    db.session.delete(quiz)
    db.session.commit()
    flash(f'Quiz "{title}" was deleted.', "success")
    return redirect(url_for("teacher"))


@app.route("/add_question/<int:quiz_id>", methods=["GET", "POST"])
@teacher_required
def add_question(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    if request.method == "POST":
        values = {key: request.form.get(key, "").strip() for key in [
            "question", "option1", "option2", "option3", "option4"
        ]}
        correct_answer = request.form.get("correct_answer", "")
        if not all(values.values()):
            flash("Please fill every question field.", "danger")
            return redirect(url_for("add_question", quiz_id=quiz.id))
        if correct_answer not in {"option1", "option2", "option3", "option4"}:
            flash("Choose a valid correct answer.", "danger")
            return redirect(url_for("add_question", quiz_id=quiz.id))
        db.session.add(Question(quiz_id=quiz.id, correct_answer=correct_answer, **values))
        db.session.commit()
        flash("Question saved successfully. You can add another question or return to the dashboard.", "success")
        return redirect(url_for("add_question", quiz_id=quiz.id))
    active_questions = [q for q in quiz.questions if q.is_active]
    return render_template("add_question.html", quiz=quiz, questions=active_questions)


@app.route("/edit_question/<int:question_id>", methods=["GET", "POST"])
@teacher_required
def edit_question(question_id):
    question = Question.query.get_or_404(question_id)
    if not question.is_active:
        flash("That question is no longer active.", "warning")
        return redirect(url_for("add_question", quiz_id=question.quiz_id))
    if request.method == "POST":
        for field in ["question", "option1", "option2", "option3", "option4"]:
            value = request.form.get(field, "").strip()
            if not value:
                flash("Please fill every question field.", "danger")
                return redirect(url_for("edit_question", question_id=question.id))
            setattr(question, field, value)
        correct = request.form.get("correct_answer", "")
        if correct not in {"option1", "option2", "option3", "option4"}:
            flash("Choose a valid correct answer.", "danger")
            return redirect(url_for("edit_question", question_id=question.id))
        question.correct_answer = correct
        db.session.commit()
        flash("Question updated.", "success")
        return redirect(url_for("add_question", quiz_id=question.quiz_id))
    return render_template("edit_question.html", question=question)


@app.post("/delete_question/<int:question_id>")
@teacher_required
def delete_question(question_id):
    question = Question.query.get_or_404(question_id)
    quiz_id = question.quiz_id
    question.is_active = False
    db.session.commit()
    flash("Question deleted from future attempts. Existing attempt records are preserved.", "success")
    return redirect(url_for("add_question", quiz_id=quiz_id))


@app.route("/student")
def student():
    quizzes = Quiz.query.order_by(Quiz.id.desc()).all()
    quizzes = [q for q in quizzes if any(question.is_active for question in q.questions)]
    return render_template("student.html", quizzes=quizzes)


@app.post("/start_quiz/<int:quiz_id>")
def start_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    questions = [q for q in quiz.questions if q.is_active]
    if not questions:
        flash("This quiz has no active questions yet.", "warning")
        return redirect(url_for("student"))
    name = request.form.get("student_name", "").strip()
    register_no = request.form.get("register_no", "").strip().upper()
    if not name or not register_no:
        flash("Enter both your name and register number.", "danger")
        return redirect(url_for("student"))

    attempt = Attempt(
        quiz_id=quiz.id,
        student_name=name,
        register_no=register_no,
        total=len(questions),
        score=0,
        status="in_progress",
    )
    db.session.add(attempt)
    db.session.commit()
    session["current_attempt_id"] = attempt.id
    session["current_question_index"] = 0
    session["question_started_at"] = time.time()
    session.pop("last_result_attempt_id", None)
    return redirect(url_for("quiz_question", attempt_id=attempt.id, question_index=0))


@app.route("/quiz/<int:attempt_id>/question/<int:question_index>", methods=["GET", "POST"])
def quiz_question(attempt_id, question_index):
    attempt = Attempt.query.get_or_404(attempt_id)
    quiz = attempt.quiz
    questions = [q for q in quiz.questions if q.is_active]

    if attempt.status != "in_progress":
        return redirect(url_for("result", attempt_id=attempt.id))
    if session.get("current_attempt_id") != attempt.id:
        flash("This quiz attempt is no longer active in this browser.", "warning")
        return redirect(url_for("student"))

    expected_index = session.get("current_question_index", 0)
    if question_index != expected_index:
        return redirect(url_for("quiz_question", attempt_id=attempt.id, question_index=expected_index))
    if question_index < 0 or question_index >= len(questions):
        return redirect(url_for("result", attempt_id=attempt.id))

    question = questions[question_index]
    if request.method == "GET":
        if "question_started_at" not in session:
            session["question_started_at"] = time.time()
        elapsed = max(0, time.time() - session["question_started_at"])
        remaining = max(0, QUESTION_TIME_LIMIT - int(elapsed))
        return render_template(
            "quiz_question.html", quiz=quiz, attempt=attempt, question=question,
            question_index=question_index, total_questions=len(questions),
            remaining=remaining, time_limit=QUESTION_TIME_LIMIT,
        )

    started = session.get("question_started_at", time.time())
    timed_out = (time.time() - started) > QUESTION_TIME_LIMIT
    selected_answer = request.form.get("answer")
    if selected_answer not in {"option1", "option2", "option3", "option4"}:
        selected_answer = None
    if timed_out:
        selected_answer = None

    is_correct = bool(not timed_out and selected_answer and selected_answer == question.correct_answer)
    db.session.add(AttemptAnswer(
        attempt_id=attempt.id,
        question_id=question.id,
        question_text=question.question,
        option1=question.option1,
        option2=question.option2,
        option3=question.option3,
        option4=question.option4,
        correct_answer=question.correct_answer,
        selected_answer=selected_answer,
        is_correct=is_correct,
        timed_out=timed_out,
    ))

    next_index = question_index + 1
    session["current_question_index"] = next_index
    if next_index >= len(questions):
        db.session.flush()
        attempt.score = sum(1 for a in attempt.answers if a.is_correct)
        attempt.total = len(questions)
        attempt.completed_at = datetime.now(timezone.utc)
        attempt.status = "completed"
        db.session.commit()
        session.pop("current_attempt_id", None)
        session.pop("current_question_index", None)
        session.pop("question_started_at", None)
        session["last_result_attempt_id"] = attempt.id
        return redirect(url_for("result", attempt_id=attempt.id))

    db.session.commit()
    session["question_started_at"] = time.time()
    return redirect(url_for("quiz_question", attempt_id=attempt.id, question_index=next_index))


@app.route("/result/<int:attempt_id>")
def result(attempt_id):
    attempt = Attempt.query.get_or_404(attempt_id)
    is_teacher = bool(session.get("teacher_authenticated"))
    is_owner = session.get("last_result_attempt_id") == attempt.id
    if not is_teacher and not is_owner:
        flash("You can only view your own quiz result.", "danger")
        return redirect(url_for("student"))

    answers = AttemptAnswer.query.filter_by(attempt_id=attempt.id).order_by(AttemptAnswer.id).all()
    review = []
    for answer in answers:
        review.append({
            "question": answer.question_text,
            "selected_text": option_text_from_answer(answer, answer.selected_answer),
            "correct_text": option_text_from_answer(answer, answer.correct_answer),
            "is_correct": answer.is_correct,
            "timed_out": answer.timed_out,
        })
    return render_template("result.html", attempt=attempt, quiz=attempt.quiz, review=review, teacher_view=is_teacher)


@app.template_filter("display_dt")
def display_dt(value):
    if not value:
        return "—"
    if value.tzinfo is None:
        return value.strftime("%d-%m-%Y %I:%M:%S %p")
    return value.astimezone().strftime("%d-%m-%Y %I:%M:%S %p")


@app.context_processor
def inject_globals():
    return {
        "question_time_limit": QUESTION_TIME_LIMIT,
        "teacher_authenticated": session.get("teacher_authenticated", False),
    }


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
