from flask import url_for
import flask_admin
from flask_admin import helpers as admin_helpers

from app_core import app, db, SERVER_MODE_WAVES, SERVER_MODE_PAYDB
from models import security, RestrictedModelView, ProposalModelView, UserModelView, TopicModelView, WavesTxModelView, PayDbApiKeyModelView, PayDbUserTransactionsView, \
    Role, User, ApiKey, PayDbTransaction, Category, Proposal, WavesTx, Topic

# Create admin
admin = flask_admin.Admin(
    app,
    'Premio Stage Admin',
    base_template='my_master.html',
    template_mode='bootstrap3',
)

# Add model views
admin.add_view(UserModelView(User, db.session, category='Admin'))
admin.add_view(RestrictedModelView(Role, db.session, category='Admin'))
admin.add_view(RestrictedModelView(Category, db.session, category='Admin'))
admin.add_view(TopicModelView(Topic, db.session, category='Admin'))
admin.add_view(ProposalModelView(Proposal, db.session))
if app.config['SERVER_MODE'] == SERVER_MODE_WAVES:
    admin.add_view(WavesTxModelView(WavesTx, db.session, name='Waves Transactions', category='Admin'))
else: # paydb
    admin.add_view(RestrictedModelView(PayDbTransaction, db.session, name='PremioPay Transactions', category='Admin'))
    admin.add_view(PayDbApiKeyModelView(ApiKey, db.session, category='User'))
    admin.add_view(PayDbUserTransactionsView(PayDbTransaction, db.session, category='User', name='PremioPay Transactions', endpoint='UserTransactions'))

# define a context processor for merging flask-admin's template context into the
# flask-security views.
@security.context_processor
def security_context_processor():
    return dict(
        admin_base_template=admin.base_template,
        admin_view=admin.index_view,
        h=admin_helpers,
        get_url=url_for
    )

