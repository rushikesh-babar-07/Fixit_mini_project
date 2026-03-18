"""
FixIt - Hyperlocal Community Issue Reporter
============================================
Team        : FixForce
Members     : Rushikesh Babar, Om Chavan, Pranav Ghadage, Sanket Bunjkar
College     : TKIET Warananagar
Guide       : Prof. P.V.Nalawade
Subject     : Mini Project (SYBTech Sem 4)
Year        : 2025-26
"""

# Import Flask and its helper functions
from flask import Flask
from flask import render_template
from flask import request
from flask import redirect
from flask import url_for
from flask import flash

# Import database library
from flask_sqlalchemy import SQLAlchemy

# Import login manager library
from flask_login import LoginManager
from flask_login import UserMixin
from flask_login import login_user
from flask_login import logout_user
from flask_login import login_required
from flask_login import current_user

# Import password hashing functions
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash

# Import file upload helper
from werkzeug.utils import secure_filename

# Import date and time
from datetime import datetime

# Import operating system functions
import os


# ─────────────────────────────────────────────
# APP SETUP
# ─────────────────────────────────────────────

# Create Flask app
app = Flask(__name__)

# Set secret key for session security
app.config['SECRET_KEY'] = 'fixit-tkiet-2026'

# Set database file location
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fixit.db'

# Disable modification tracking
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Set uploads folder path
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')

# Set maximum file size to 5MB
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# Allowed image extensions
ALLOWED_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp']

# Create database object
db = SQLAlchemy(app)

# Create login manager object
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please login to continue.'
login_manager.login_message_category = 'warning'


# ─────────────────────────────────────────────
# DATABASE MODELS
# ─────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20), default='citizen')
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    issues = db.relationship('Issue', backref='author', lazy=True, foreign_keys='Issue.user_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        result = check_password_hash(self.password_hash, password)
        return result


class Issue(db.Model):
    __tablename__ = 'issues'

    id             = db.Column(db.Integer, primary_key=True)
    title          = db.Column(db.String(150), nullable=False)
    description    = db.Column(db.Text, nullable=False)
    category       = db.Column(db.String(50), nullable=False)
    location       = db.Column(db.String(200), nullable=False)
    photo          = db.Column(db.String(200), default=None)
    status         = db.Column(db.String(30), default='reported')
    upvotes        = db.Column(db.Integer, default=0)
    priority_score = db.Column(db.Float, default=0.0)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow)

    votes = db.relationship('Vote', backref='issue', lazy=True, cascade='all, delete-orphan')


class Vote(db.Model):
    __tablename__ = 'votes'

    id       = db.Column(db.Integer, primary_key=True)
    user_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    issue_id = db.Column(db.Integer, db.ForeignKey('issues.id'), nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'issue_id'),)


# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    return user


def check_allowed_file(filename):
    if '.' not in filename:
        return False
    extension = filename.rsplit('.', 1)[1]
    extension = extension.lower()
    if extension in ALLOWED_EXTENSIONS:
        return True
    else:
        return False


# ─────────────────────────────────────────────
# PRIORITY SCORE CALCULATOR
# ─────────────────────────────────────────────

def calculate_priority_score(issue):
    """
    Formula:
    priority_score = (upvotes x 2) + (days_open x 1.5) + category_weight

    Category Weights:
    Water       = 5
    Electricity = 4
    Road        = 3
    Garbage     = 2
    Other       = 1
    """

    # Step 1 - Get upvotes
    upvotes_count = issue.upvotes

    # Step 2 - Calculate upvotes score
    upvotes_score = upvotes_count * 2

    # Step 3 - Calculate days open
    today         = datetime.utcnow()
    created_date  = issue.created_at
    difference    = today - created_date
    days_open     = difference.days

    # Step 4 - Calculate days score
    days_score = days_open * 1.5

    # Step 5 - Get category weight
    category = issue.category

    if category == 'Water':
        category_weight = 5
    elif category == 'Electricity':
        category_weight = 4
    elif category == 'Road':
        category_weight = 3
    elif category == 'Garbage':
        category_weight = 2
    else:
        category_weight = 1

    # Step 6 - Calculate final score
    priority_score = upvotes_score + days_score + category_weight

    # Step 7 - Round to 1 decimal
    priority_score = round(priority_score, 1)

    return priority_score


def update_all_priority_scores():
    all_issues = Issue.query.all()
    for issue in all_issues:
        new_score = calculate_priority_score(issue)
        issue.priority_score = new_score
    db.session.commit()


# ─────────────────────────────────────────────
# MONTHLY REPORT GENERATOR
# ─────────────────────────────────────────────

def generate_monthly_report():
    # Get all issues
    all_issues = Issue.query.all()

    # Empty dictionary for monthly data
    monthly_data = {}

    # Loop through each issue
    for issue in all_issues:

        # Get month and year
        month_number = issue.created_at.month
        year_number  = issue.created_at.year
        month_name   = issue.created_at.strftime('%B')
        month_key    = month_name + ' ' + str(year_number)

        # Add month to dictionary if not exists
        if month_key not in monthly_data:
            monthly_data[month_key] = {
                'month'       : month_key,
                'total'       : 0,
                'fixed'       : 0,
                'in_progress' : 0,
                'reported'    : 0,
                'fix_rate'    : 0.0,
                'sort_key'    : str(year_number) + str(month_number).zfill(2)
            }

        # Increase total
        monthly_data[month_key]['total'] = monthly_data[month_key]['total'] + 1

        # Increase status count
        if issue.status == 'fixed':
            monthly_data[month_key]['fixed'] = monthly_data[month_key]['fixed'] + 1
        elif issue.status == 'in_progress':
            monthly_data[month_key]['in_progress'] = monthly_data[month_key]['in_progress'] + 1
        else:
            monthly_data[month_key]['reported'] = monthly_data[month_key]['reported'] + 1

    # Calculate fix rate for each month
    for month_key in monthly_data:
        total_count = monthly_data[month_key]['total']
        fixed_count = monthly_data[month_key]['fixed']

        if total_count > 0:
            fix_rate = (fixed_count / total_count) * 100
            fix_rate = round(fix_rate, 1)
            monthly_data[month_key]['fix_rate'] = fix_rate
        else:
            monthly_data[month_key]['fix_rate'] = 0.0

    # Convert to list and sort newest first
    monthly_list = list(monthly_data.values())
    monthly_list = sorted(monthly_list, key=lambda x: x['sort_key'], reverse=True)

    return monthly_list


def calculate_category_stats():
    all_issues = Issue.query.all()
    total      = len(all_issues)

    road_count        = 0
    water_count       = 0
    electricity_count = 0
    garbage_count     = 0
    other_count       = 0

    for issue in all_issues:
        if issue.category == 'Road':
            road_count = road_count + 1
        elif issue.category == 'Water':
            water_count = water_count + 1
        elif issue.category == 'Electricity':
            electricity_count = electricity_count + 1
        elif issue.category == 'Garbage':
            garbage_count = garbage_count + 1
        else:
            other_count = other_count + 1

    if total > 0:
        road_pct        = round((road_count / total) * 100, 1)
        water_pct       = round((water_count / total) * 100, 1)
        electricity_pct = round((electricity_count / total) * 100, 1)
        garbage_pct     = round((garbage_count / total) * 100, 1)
        other_pct       = round((other_count / total) * 100, 1)
    else:
        road_pct = water_pct = electricity_pct = garbage_pct = other_pct = 0

    category_stats = {
        'Road'        : {'count': road_count,        'percent': road_pct},
        'Water'       : {'count': water_count,       'percent': water_pct},
        'Electricity' : {'count': electricity_count, 'percent': electricity_pct},
        'Garbage'     : {'count': garbage_count,     'percent': garbage_pct},
        'Other'       : {'count': other_count,       'percent': other_pct},
    }

    return category_stats


# ─────────────────────────────────────────────
# ROUTES — AUTH
# ─────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name             = request.form.get('name')
        email            = request.form.get('email')
        password         = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        name  = name.strip()
        email = email.strip()
        email = email.lower()

        if name == '' or email == '' or password == '':
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('register.html')

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered. Please login.', 'danger')
            return render_template('register.html')

        new_user = User()
        new_user.name  = name
        new_user.email = email
        new_user.role  = 'citizen'
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash('Account created! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email    = request.form.get('email')
        password = request.form.get('password')

        email = email.strip()
        email = email.lower()

        user = User.query.filter_by(email=email).first()

        if user is None:
            flash('Email not found. Please register.', 'danger')
            return render_template('login.html')

        password_correct = user.check_password(password)

        if password_correct == False:
            flash('Wrong password. Try again.', 'danger')
            return render_template('login.html')

        login_user(user)
        flash('Welcome back, ' + user.name + '!', 'success')
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))


# ─────────────────────────────────────────────
# ROUTES — ISSUES
# ─────────────────────────────────────────────

@app.route('/')
def index():
    update_all_priority_scores()

    selected_category = request.args.get('category', '')
    selected_status   = request.args.get('status', '')
    search_keyword    = request.args.get('search', '')

    all_issues      = Issue.query.all()
    filtered_issues = []

    for issue in all_issues:
        if selected_category != '':
            if issue.category != selected_category:
                continue

        if selected_status != '':
            if issue.status != selected_status:
                continue

        if search_keyword != '':
            keyword_lower     = search_keyword.lower()
            found_in_title    = keyword_lower in issue.title.lower()
            found_in_desc     = keyword_lower in issue.description.lower()
            found_in_location = keyword_lower in issue.location.lower()

            if found_in_title == False and found_in_desc == False and found_in_location == False:
                continue

        filtered_issues.append(issue)

    filtered_issues = sorted(filtered_issues, key=lambda x: x.priority_score, reverse=True)

    voted_issue_ids = []
    if current_user.is_authenticated:
        all_votes = Vote.query.filter_by(user_id=current_user.id).all()
        for vote in all_votes:
            voted_issue_ids.append(vote.issue_id)

    total_count       = len(all_issues)
    fixed_count       = 0
    in_progress_count = 0

    for issue in all_issues:
        if issue.status == 'fixed':
            fixed_count = fixed_count + 1
        elif issue.status == 'in_progress':
            in_progress_count = in_progress_count + 1

    return render_template(
        'index.html',
        issues            = filtered_issues,
        voted_issue_ids   = voted_issue_ids,
        total_count       = total_count,
        fixed_count       = fixed_count,
        in_progress_count = in_progress_count,
        selected_category = selected_category,
        selected_status   = selected_status,
        search_keyword    = search_keyword
    )


@app.route('/report', methods=['GET', 'POST'])
@login_required
def report_issue():
    if request.method == 'POST':
        title       = request.form.get('title')
        description = request.form.get('description')
        category    = request.form.get('category')
        location    = request.form.get('location')

        title       = title.strip()
        description = description.strip()
        location    = location.strip()

        if title == '' or description == '' or category == '' or location == '':
            flash('All fields are required.', 'danger')
            return render_template('report.html')

        photo_filename = None

        if 'photo' in request.files:
            photo_file = request.files['photo']

            if photo_file.filename != '':
                file_allowed = check_allowed_file(photo_file.filename)

                if file_allowed:
                    safe_name      = secure_filename(photo_file.filename)
                    timestamp      = datetime.now().strftime('%Y%m%d_%H%M%S_')
                    photo_filename = timestamp + safe_name
                    save_path      = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
                    photo_file.save(save_path)
                else:
                    flash('File type not allowed.', 'danger')
                    return render_template('report.html')

        new_issue                = Issue()
        new_issue.title          = title
        new_issue.description    = description
        new_issue.category       = category
        new_issue.location       = location
        new_issue.photo          = photo_filename
        new_issue.status         = 'reported'
        new_issue.upvotes        = 0
        new_issue.priority_score = 0.0
        new_issue.user_id        = current_user.id

        db.session.add(new_issue)
        db.session.commit()

        flash('Issue reported successfully!', 'success')
        return redirect(url_for('index'))

    return render_template('report.html')


@app.route('/issue/<int:issue_id>')
def view_issue(issue_id):
    issue     = Issue.query.get_or_404(issue_id)
    has_voted = False

    if current_user.is_authenticated:
        existing_vote = Vote.query.filter_by(user_id=current_user.id, issue_id=issue_id).first()
        if existing_vote is not None:
            has_voted = True

    score = calculate_priority_score(issue)

    return render_template('issue_detail.html', issue=issue, has_voted=has_voted, score=score)


@app.route('/upvote/<int:issue_id>', methods=['POST'])
@login_required
def upvote(issue_id):
    issue         = Issue.query.get_or_404(issue_id)
    existing_vote = Vote.query.filter_by(user_id=current_user.id, issue_id=issue_id).first()

    if existing_vote is not None:
        db.session.delete(existing_vote)
        issue.upvotes = issue.upvotes - 1
        if issue.upvotes < 0:
            issue.upvotes = 0
        db.session.commit()
        flash('Vote removed.', 'info')
    else:
        new_vote          = Vote()
        new_vote.user_id  = current_user.id
        new_vote.issue_id = issue_id
        db.session.add(new_vote)
        issue.upvotes = issue.upvotes + 1
        db.session.commit()
        flash('Upvoted!', 'success')

    return redirect(request.referrer or url_for('index'))


@app.route('/delete/<int:issue_id>', methods=['POST'])
@login_required
def delete_issue(issue_id):
    issue = Issue.query.get_or_404(issue_id)

    if issue.user_id != current_user.id and current_user.role != 'admin':
        flash('You can only delete your own issues.', 'danger')
        return redirect(url_for('index'))

    if issue.photo is not None:
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], issue.photo)
        if os.path.exists(photo_path):
            os.remove(photo_path)

    db.session.delete(issue)
    db.session.commit()
    flash('Issue deleted.', 'success')
    return redirect(url_for('index'))


@app.route('/my_issues')
@login_required
def my_issues():
    my_issue_list = Issue.query.filter_by(user_id=current_user.id).all()
    my_issue_list = sorted(my_issue_list, key=lambda x: x.created_at, reverse=True)
    return render_template('my_issues.html', issues=my_issue_list)


# ─────────────────────────────────────────────
# ROUTES — ADMIN
# ─────────────────────────────────────────────

@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    update_all_priority_scores()

    all_issues = Issue.query.all()
    all_issues = sorted(all_issues, key=lambda x: x.priority_score, reverse=True)

    total_users       = User.query.count()
    total_issues      = len(all_issues)
    fixed_count       = 0
    in_progress_count = 0
    reported_count    = 0

    for issue in all_issues:
        if issue.status == 'fixed':
            fixed_count = fixed_count + 1
        elif issue.status == 'in_progress':
            in_progress_count = in_progress_count + 1
        else:
            reported_count = reported_count + 1

    return render_template(
        'admin.html',
        issues            = all_issues,
        total_users       = total_users,
        total_issues      = total_issues,
        fixed_count       = fixed_count,
        in_progress_count = in_progress_count,
        reported_count    = reported_count
    )


@app.route('/admin/update/<int:issue_id>', methods=['POST'])
@login_required
def update_status(issue_id):
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    issue      = Issue.query.get_or_404(issue_id)
    new_status = request.form.get('status')

    if new_status == 'reported' or new_status == 'in_progress' or new_status == 'fixed':
        issue.status     = new_status
        issue.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Status updated!', 'success')
    else:
        flash('Invalid status.', 'danger')

    return redirect(url_for('admin_panel'))


@app.route('/monthly_report')
@login_required
def monthly_report():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    monthly_data   = generate_monthly_report()
    category_stats = calculate_category_stats()

    all_issues    = Issue.query.all()
    total_issues  = len(all_issues)
    total_fixed   = 0
    total_in_prog = 0
    total_reported = 0

    for issue in all_issues:
        if issue.status == 'fixed':
            total_fixed = total_fixed + 1
        elif issue.status == 'in_progress':
            total_in_prog = total_in_prog + 1
        else:
            total_reported = total_reported + 1

    if total_issues > 0:
        overall_fix_rate = (total_fixed / total_issues) * 100
        overall_fix_rate = round(overall_fix_rate, 1)
    else:
        overall_fix_rate = 0.0

    return render_template(
        'monthly_report.html',
        monthly_data     = monthly_data,
        category_stats   = category_stats,
        total_issues     = total_issues,
        total_fixed      = total_fixed,
        total_in_prog    = total_in_prog,
        total_reported   = total_reported,
        overall_fix_rate = overall_fix_rate
    )


# ─────────────────────────────────────────────
# RUN APP
# ─────────────────────────────────────────────

def create_tables():
    with app.app_context():
        db.create_all()

        admin_exists = User.query.filter_by(email='admin@fixit.com').first()

        if admin_exists is None:
            admin_user = User()
            admin_user.name  = 'Admin'
            admin_user.email = 'admin@fixit.com'
            admin_user.role  = 'admin'
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
            print('Admin created: admin@fixit.com / admin123')

        print('Database ready!')


create_tables()

if __name__ == '__main__':
    app.run(debug=True)
