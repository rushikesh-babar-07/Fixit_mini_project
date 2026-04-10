"""
FixIt - Hyperlocal Community Issue Reporter
============================================
Team        : FixForce
Members     : Rushikesh Babar, Om Chavan 
College     : TKIET Warananagar
Guide       : Prof. P.V.Nalawade
Subject     : Mini Project (SYBTech Sem 4)
Year        : 2025-26
"""

#  IMPORTS 

from flask import Flask
from flask import render_template
from flask import request
from flask import redirect
from flask import url_for
from flask import flash
from flask import jsonify

from flask_sqlalchemy import SQLAlchemy

from flask_login import LoginManager
from flask_login import UserMixin
from flask_login import login_user
from flask_login import logout_user
from flask_login import login_required
from flask_login import current_user

from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from datetime import datetime
import os

# APP SETUP 

app = Flask(__name__)

app.config['SECRET_KEY']                  = 'fixit-competition-2026'
app.config['SQLALCHEMY_DATABASE_URI']     = 'sqlite:///fixit.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER']              = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH']         = 5 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp']

db           = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view             = 'login'
login_manager.login_message          = 'Please login to continue.'
login_manager.login_message_category = 'error'

#  MODELS

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20), default='citizen')
    bio           = db.Column(db.String(200), default='')
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    issues   = db.relationship('Issue', backref='author', lazy=True, foreign_keys='Issue.user_id')
    comments = db.relationship('Comment', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def total_issues(self):
        return len(self.issues)

    def total_upvotes_received(self):
        total = 0
        for issue in self.issues:
            total = total + issue.upvotes
        return total


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

    votes    = db.relationship('Vote', backref='issue', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='issue', lazy=True, cascade='all, delete-orphan')

    def days_open(self):
        today      = datetime.utcnow()
        difference = today - self.created_at
        return difference.days

    def comment_count(self):
        return len(self.comments)


class Vote(db.Model):
    __tablename__ = 'votes'

    id       = db.Column(db.Integer, primary_key=True)
    user_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    issue_id = db.Column(db.Integer, db.ForeignKey('issues.id'), nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'issue_id'),)


class Comment(db.Model):
    __tablename__ = 'comments'

    id         = db.Column(db.Integer, primary_key=True)
    content    = db.Column(db.Text, nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    issue_id   = db.Column(db.Integer, db.ForeignKey('issues.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# HELPERS 

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def check_allowed_file(filename):
    if '.' not in filename:
        return False
    extension = filename.rsplit('.', 1)[1].lower()
    if extension in ALLOWED_EXTENSIONS:
        return True
    return False


# PRIORITY SCORE CALCULATOR 

def calculate_priority_score(issue):
    # upvotes score
    upvotes_score = issue.upvotes * 2

    # days open score
    today        = datetime.utcnow()
    difference   = today - issue.created_at
    days_open    = difference.days
    days_score   = days_open * 1.5

    # category weight
    if issue.category == 'Water':
        weight = 5
    elif issue.category == 'Electricity':
        weight = 4
    elif issue.category == 'Road':
        weight = 3
    elif issue.category == 'Garbage':
        weight = 2
    else:
        weight = 1

    # final score
    score = upvotes_score + days_score + weight
    score = round(score, 1)

    return score


def update_all_scores():
    all_issues = Issue.query.all()
    for issue in all_issues:
        issue.priority_score = calculate_priority_score(issue)
    db.session.commit()


#  MONTHLY REPORT 

def generate_monthly_report():
    all_issues   = Issue.query.all()
    monthly_data = {}

    for issue in all_issues:
        month_name = issue.created_at.strftime('%B')
        year       = str(issue.created_at.year)
        month_num  = str(issue.created_at.month).zfill(2)
        key        = month_name + ' ' + year

        if key not in monthly_data:
            monthly_data[key] = {
                'month'       : key,
                'total'       : 0,
                'fixed'       : 0,
                'in_progress' : 0,
                'reported'    : 0,
                'fix_rate'    : 0.0,
                'sort_key'    : year + month_num
            }

        monthly_data[key]['total'] = monthly_data[key]['total'] + 1

        if issue.status == 'fixed':
            monthly_data[key]['fixed'] = monthly_data[key]['fixed'] + 1
        elif issue.status == 'in_progress':
            monthly_data[key]['in_progress'] = monthly_data[key]['in_progress'] + 1
        else:
            monthly_data[key]['reported'] = monthly_data[key]['reported'] + 1

    for key in monthly_data:
        total = monthly_data[key]['total']
        fixed = monthly_data[key]['fixed']
        if total > 0:
            monthly_data[key]['fix_rate'] = round((fixed / total) * 100, 1)

    result = list(monthly_data.values())
    result = sorted(result, key=lambda x: x['sort_key'], reverse=True)
    return result


def calculate_category_stats():
    all_issues = Issue.query.all()
    total      = len(all_issues)

    stats = {
        'Road': 0, 'Water': 0,
        'Electricity': 0, 'Garbage': 0, 'Other': 0
    }

    for issue in all_issues:
        if issue.category in stats:
            stats[issue.category] = stats[issue.category] + 1

    result = {}
    for cat in stats:
        count = stats[cat]
        if total > 0:
            percent = round((count / total) * 100, 1)
        else:
            percent = 0
        result[cat] = {'count': count, 'percent': percent}

    return result


# LEADERBOARD 

def get_leaderboard():
    all_users = User.query.filter_by(role='citizen').all()

    leaderboard = []
    for user in all_users:
        issues_count  = user.total_issues()
        upvotes_count = user.total_upvotes_received()
        fixed_count   = 0

        for issue in user.issues:
            if issue.status == 'fixed':
                fixed_count = fixed_count + 1

        impact_score = (issues_count * 5) + (upvotes_count * 2) + (fixed_count * 10)

        leaderboard.append({
            'user'         : user,
            'issues_count' : issues_count,
            'upvotes'      : upvotes_count,
            'fixed'        : fixed_count,
            'impact_score' : impact_score
        })

    leaderboard = sorted(leaderboard, key=lambda x: x['impact_score'], reverse=True)
    return leaderboard


# AUTH ROUTES

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name             = request.form.get('name', '').strip()
        email            = request.form.get('email', '').strip().lower()
        password         = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if name == '' or email == '' or password == '':
            flash('All fields are required.', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
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
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()

        if user is None:
            flash('Email not found.', 'error')
            return render_template('login.html')

        if user.check_password(password) == False:
            flash('Wrong password.', 'error')
            return render_template('login.html')

        login_user(user)
        flash('Welcome back, ' + user.name + '! 👋', 'success')
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))


#  ISSUE ROUTES 

@app.route('/')
def index():
    update_all_scores()

    selected_category = request.args.get('category', '')
    selected_status   = request.args.get('status', '')
    search_keyword    = request.args.get('search', '')
    sort_by           = request.args.get('sort', 'priority')

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
            kw = search_keyword.lower()
            if kw not in issue.title.lower() and kw not in issue.description.lower() and kw not in issue.location.lower():
                continue
        filtered_issues.append(issue)

    if sort_by == 'newest':
        filtered_issues = sorted(filtered_issues, key=lambda x: x.created_at, reverse=True)
    elif sort_by == 'upvotes':
        filtered_issues = sorted(filtered_issues, key=lambda x: x.upvotes, reverse=True)
    else:
        filtered_issues = sorted(filtered_issues, key=lambda x: x.priority_score, reverse=True)

    voted_ids = []
    if current_user.is_authenticated:
        all_votes = Vote.query.filter_by(user_id=current_user.id).all()
        for vote in all_votes:
            voted_ids.append(vote.issue_id)

    total_count       = len(all_issues)
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
        'index.html',
        issues            = filtered_issues,
        voted_ids         = voted_ids,
        total_count       = total_count,
        fixed_count       = fixed_count,
        in_progress_count = in_progress_count,
        reported_count    = reported_count,
        selected_category = selected_category,
        selected_status   = selected_status,
        search_keyword    = search_keyword,
        sort_by           = sort_by
    )


@app.route('/report', methods=['GET', 'POST'])
@login_required
def report_issue():
    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category    = request.form.get('category', '')
        location    = request.form.get('location', '').strip()

        if title == '' or description == '' or category == '' or location == '':
            flash('All fields are required.', 'error')
            return render_template('report.html')

        photo_filename = None

        if 'photo' in request.files:
            photo_file = request.files['photo']
            if photo_file.filename != '':
                if check_allowed_file(photo_file.filename):
                    safe_name      = secure_filename(photo_file.filename)
                    timestamp      = datetime.now().strftime('%Y%m%d_%H%M%S_')
                    photo_filename = timestamp + safe_name
                    save_path      = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
                    photo_file.save(save_path)
                else:
                    flash('File type not allowed.', 'error')
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

        flash('Issue reported successfully! The community can now see it. 🎉', 'success')
        return redirect(url_for('index'))

    return render_template('report.html')


@app.route('/issue/<int:issue_id>', methods=['GET', 'POST'])
def view_issue(issue_id):
    issue = Issue.query.get_or_404(issue_id)

    # Handle comment submission
    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash('Please login to comment.', 'error')
            return redirect(url_for('login'))

        content = request.form.get('content', '').strip()
        if content == '':
            flash('Comment cannot be empty.', 'error')
        else:
            new_comment          = Comment()
            new_comment.content  = content
            new_comment.user_id  = current_user.id
            new_comment.issue_id = issue_id
            db.session.add(new_comment)
            db.session.commit()
            flash('Comment added!', 'success')

        return redirect(url_for('view_issue', issue_id=issue_id))

    has_voted = False
    if current_user.is_authenticated:
        existing_vote = Vote.query.filter_by(user_id=current_user.id, issue_id=issue_id).first()
        if existing_vote is not None:
            has_voted = True

    score    = calculate_priority_score(issue)
    comments = Comment.query.filter_by(issue_id=issue_id).order_by(Comment.created_at.desc()).all()

    return render_template('issue_detail.html', issue=issue, has_voted=has_voted, score=score, comments=comments)


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
        flash('Upvoted! 👍', 'success')

    return redirect(request.referrer or url_for('index'))


@app.route('/delete/<int:issue_id>', methods=['POST'])
@login_required
def delete_issue(issue_id):
    issue = Issue.query.get_or_404(issue_id)

    if issue.user_id != current_user.id and current_user.role != 'admin':
        flash('You can only delete your own issues.', 'error')
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


@app.route('/profile')
@login_required
def profile():
    user_issues  = Issue.query.filter_by(user_id=current_user.id).all()
    fixed_issues = []
    for issue in user_issues:
        if issue.status == 'fixed':
            fixed_issues.append(issue)

    total_upvotes = current_user.total_upvotes_received()
    return render_template('profile.html',
        user_issues   = user_issues,
        fixed_issues  = fixed_issues,
        total_upvotes = total_upvotes
    )


@app.route('/leaderboard')
def leaderboard():
    leaderboard_data = get_leaderboard()
    return render_template('leaderboard.html', leaderboard=leaderboard_data)


# ADMIN ROUTES 

@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('index'))

    update_all_scores()

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

    return render_template('admin.html',
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
        flash('Access denied.', 'error')
        return redirect(url_for('index'))

    issue      = Issue.query.get_or_404(issue_id)
    new_status = request.form.get('status')

    if new_status in ['reported', 'in_progress', 'fixed']:
        issue.status     = new_status
        issue.updated_at = datetime.utcnow()
        db.session.commit()
        flash('Status updated! ✅', 'success')

    return redirect(url_for('admin_panel'))


@app.route('/monthly_report')
@login_required
def monthly_report():
    if current_user.role != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('index'))

    monthly_data   = generate_monthly_report()
    category_stats = calculate_category_stats()

    all_issues     = Issue.query.all()
    total_issues   = len(all_issues)
    total_fixed    = 0
    total_in_prog  = 0
    total_reported = 0

    for issue in all_issues:
        if issue.status == 'fixed':
            total_fixed = total_fixed + 1
        elif issue.status == 'in_progress':
            total_in_prog = total_in_prog + 1
        else:
            total_reported = total_reported + 1

    if total_issues > 0:
        overall_fix_rate = round((total_fixed / total_issues) * 100, 1)
    else:
        overall_fix_rate = 0.0

    return render_template('monthly_report.html',
        monthly_data     = monthly_data,
        category_stats   = category_stats,
        total_issues     = total_issues,
        total_fixed      = total_fixed,
        total_in_prog    = total_in_prog,
        total_reported   = total_reported,
        overall_fix_rate = overall_fix_rate
    )


# INIT 

def create_tables():
    with app.app_context():
        db.create_all()

        if User.query.filter_by(email='admin@fixit.com').first() is None:
            admin = User()
            admin.name  = 'Admin'
            admin.email = 'admin@fixit.com'
            admin.role  = 'admin'
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('Admin created!')

        print('Database ready!')


create_tables()

if __name__ == '__main__':
    app.run(debug=True)