from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    projects = db.relationship('Project', backref='user', lazy=True)

    def get_id(self):
        return str(self.id)

class SystemSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    serper_api_key = db.Column(db.String(200))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    updated_by = db.relationship('User', backref='system_settings_updates')

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    keyword = db.Column(db.String(100), nullable=False)
    target_business = db.Column(db.String(200), nullable=False)
    center_coordinates = db.Column(db.String(100), nullable=False)
    radius_km = db.Column(db.Float, default=2.0)
    num_points = db.Column(db.Integer, default=16)
    shape = db.Column(db.String(20), default='circle')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    analyses = db.relationship('Analysis', backref='project', lazy=True)

class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    analysis_date = db.Column(db.DateTime, default=datetime.utcnow)
    total_points = db.Column(db.Integer)
    visible_points = db.Column(db.Integer)
    average_position = db.Column(db.Float)
    best_position = db.Column(db.Integer)
    worst_position = db.Column(db.Integer)
    visibility_rate = db.Column(db.Float)
    map_file_path = db.Column(db.String(200))
    analysis_file_path = db.Column(db.String(200))
    points = db.relationship('AnalysisPoint', backref='analysis', lazy=True)

class AnalysisPoint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analysis.id'), nullable=False)
    coordinates = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    position = db.Column(db.Integer)
    rating = db.Column(db.Float)
    rating_count = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ScheduledAnalysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    frequency = db.Column(db.String(50), nullable=False)  # daily, weekly, monthly
    last_run = db.Column(db.DateTime)
    next_run = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow) 