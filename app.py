import os, sqlite3, uuid, secrets, json
from datetime import datetime, date
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
INSTANCE = BASE / 'instance'; INSTANCE.mkdir(exist_ok=True)
UPLOAD_ROOT = Path(os.environ.get('UPLOAD_DIR', BASE / 'static' / 'uploads'))
for sub in ['students','notes','videos','gallery','questions','site']:
    (UPLOAD_ROOT/sub).mkdir(parents=True, exist_ok=True)
DB_PATH = os.environ.get('DATABASE_PATH', str(INSTANCE/'gca_academy.db'))
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-before-deployment-' + secrets.token_hex(12))
app.config['MAX_CONTENT_LENGTH'] = 250 * 1024 * 1024
app.config['UPLOAD_ROOT'] = str(UPLOAD_ROOT)
ALLOWED = {'png','jpg','jpeg','webp','pdf','mp4','webm','mov','doc','docx','ppt','pptx','txt'}


def db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn

def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY AUTOINCREMENT, student_code TEXT UNIQUE, name TEXT NOT NULL, father TEXT, mother TEXT, dob TEXT, gender TEXT, phone TEXT, email TEXT, address TEXT, class_name TEXT, course TEXT, admission_date TEXT, photo TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS resources (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, category TEXT, class_name TEXT, description TEXT, file_path TEXT, external_url TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS exams (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, class_name TEXT, exam_date TEXT, total_marks INTEGER DEFAULT 100, details TEXT);
        CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, amount REAL, paid_on TEXT, method TEXT, reference TEXT, note TEXT, FOREIGN KEY(student_id) REFERENCES students(id));
        CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, class_date TEXT, status TEXT, note TEXT, UNIQUE(student_id,class_date), FOREIGN KEY(student_id) REFERENCES students(id));
        CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY AUTOINCREMENT, class_name TEXT, subject TEXT, chapter TEXT, question TEXT, a TEXT, b TEXT, c TEXT, d TEXT, answer TEXT, explanation TEXT);
        CREATE TABLE IF NOT EXISTS mcq_results (id INTEGER PRIMARY KEY AUTOINCREMENT, student_name TEXT, class_name TEXT, score INTEGER, total INTEGER, attempted_at TEXT);
        CREATE TABLE IF NOT EXISTS gallery (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, image_path TEXT, caption TEXT, created_at TEXT);
        ''')
        defaults = {'academy_name':'GCA COACHING ACADEMY','tagline':'Learn Today, Lead Tomorrow','address':'Marangapalli, P.O. Ganjpara, P.S. Raighar, Nabarangpur, Odisha – 764074','phone':'8280897689','email':'gca.mrp.edu@gmail.com','logo':'','hero_title':'Build Your Bright Future','hero_text':'Admissions, learning materials, online classes and exams — all in one place.','primary_color':'#17365d','accent_color':'#d7a83e','footer_text':'GCA Coaching Academy • Learn Every Day'}
        for k,v in defaults.items(): c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(k,v))
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',('admin_password_hash',generate_password_hash(os.environ.get('ADMIN_PASSWORD','GcaAdmin@123'))))

def settings():
    with db() as c: return {r['key']:r['value'] for r in c.execute('SELECT key,value FROM settings')}

def save_setting(key,value):
    with db() as c: c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))

def allowed_file(name): return '.' in name and name.rsplit('.',1)[1].lower() in ALLOWED

def save_upload(file, folder, allowed=None):
    if not file or not file.filename: return ''
    if not allowed_file(file.filename): raise ValueError('File type not allowed.')
    ext=file.filename.rsplit('.',1)[1].lower(); name=f'{uuid.uuid4().hex}.{ext}'
    target=UPLOAD_ROOT/folder/name; target.parent.mkdir(parents=True,exist_ok=True); file.save(target)
    return f'{folder}/{name}'

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        if not session.get('admin'): return redirect(url_for('admin_login',next=request.path))
        return fn(*args,**kwargs)
    return wrapper

@app.context_processor
def inject_globals(): return {'site':settings(),'admin_logged_in':bool(session.get('admin')),'year':datetime.now().year}

@app.route('/')
def home():
    with db() as c:
        resources=c.execute('SELECT * FROM resources ORDER BY id DESC LIMIT 6').fetchall()
        exams=c.execute('SELECT * FROM exams ORDER BY exam_date DESC LIMIT 4').fetchall()
        gallery=c.execute('SELECT * FROM gallery ORDER BY id DESC LIMIT 6').fetchall()
    return render_template('home.html',resources=resources,exams=exams,gallery=gallery)

@app.route('/admission', methods=['GET','POST'])
def admission():
    if request.method=='POST':
        f=request.form
        required=['name','class_name','phone']
        if any(not f.get(k,'').strip() for k in required): flash('Please fill student name, class and mobile number.','error'); return redirect(url_for('admission'))
        try: photo=save_upload(request.files.get('photo'),'students')
        except ValueError as e: flash(str(e),'error'); return redirect(url_for('admission'))
        code='GCA'+datetime.now().strftime('%y%m%d')+secrets.token_hex(2).upper()
        with db() as c:
            cur=c.execute('''INSERT INTO students(student_code,name,father,mother,dob,gender,phone,email,address,class_name,course,admission_date,photo,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (code,f['name'].strip(),f.get('father',''),f.get('mother',''),f.get('dob',''),f.get('gender',''),f['phone'].strip(),f.get('email',''),f.get('address',''),f['class_name'],f.get('course',''),date.today().isoformat(),photo,datetime.now().isoformat(timespec='seconds')))
            sid=cur.lastrowid
        sync_student_to_google_sheet(sid)
        return redirect(url_for('admission_success',student_id=sid))
    return render_template('admission.html')

@app.route('/admission/success/<int:student_id>')
def admission_success(student_id):
    with db() as c: student=c.execute('SELECT * FROM students WHERE id=?',(student_id,)).fetchone()
    if not student: abort(404)
    return render_template('admission_success.html',student=student)

@app.route('/student/<int:student_id>/admission.pdf')
def admission_pdf(student_id):
    with db() as c: s=c.execute('SELECT * FROM students WHERE id=?',(student_id,)).fetchone()
    if not s: abort(404)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib import colors
        from io import BytesIO
        buffer=BytesIO(); p=canvas.Canvas(buffer,pagesize=A4); w,h=A4; st=settings()
        p.setFillColor(colors.HexColor(st.get('primary_color','#17365d'))); p.rect(0,h-105,w,105,fill=1,stroke=0)
        p.setFillColor(colors.white); p.setFont('Helvetica-Bold',19); p.drawString(48,h-50,st.get('academy_name','GCA COACHING ACADEMY')[:45])
        p.setFont('Helvetica',10); p.drawString(48,h-72,st.get('address','')[:95]); p.drawString(48,h-88,f"Phone: {st.get('phone','')}  Email: {st.get('email','')}")
        p.setFillColor(colors.HexColor('#172b45')); p.setFont('Helvetica-Bold',16); p.drawString(48,h-150,'ADMISSION CONFIRMATION')
        p.setFillColor(colors.HexColor('#d7a83e')); p.rect(48,h-164,120,3,fill=1,stroke=0)
        fields=[('Student ID',s['student_code']),('Student Name',s['name']),("Father's Name",s['father'] or '-'),("Mother's Name",s['mother'] or '-'),('Date of Birth',s['dob'] or '-'),('Gender',s['gender'] or '-'),('Class',s['class_name']),('Course / Batch',s['course'] or '-'),('Mobile',s['phone']),('Email',s['email'] or '-'),('Address',s['address'] or '-'),('Admission Date',s['admission_date'] or '-')]
        y=h-205
        for label,val in fields:
            p.setFillColor(colors.HexColor('#64748b')); p.setFont('Helvetica-Bold',10); p.drawString(50,y,label)
            p.setFillColor(colors.HexColor('#172b45')); p.setFont('Helvetica',10); p.drawString(175,y,str(val)[:95]); y-=29
        if s['photo']:
            img=BASE/'static'/'uploads'/s['photo']
            if img.exists():
                try: p.drawImage(str(img),w-145,h-295,width=85,height=100,preserveAspectRatio=True,anchor='c',mask='auto')
                except Exception: pass
        p.setFillColor(colors.HexColor('#64748b')); p.setFont('Helvetica',8); p.drawString(48,45,'This document confirms that the admission form was submitted. Keep it for your records.')
        p.save(); buffer.seek(0)
        return send_file(buffer,as_attachment=True,download_name=f'{s["student_code"]}_Admission.pdf',mimetype='application/pdf')
    except ImportError:
        flash('PDF library missing. Run pip install -r requirements.txt','error'); return redirect(url_for('admission_success',student_id=student_id))

@app.route('/student/<int:student_id>/id-card.pdf')
def id_card_pdf(student_id):
    with db() as c: s=c.execute('SELECT * FROM students WHERE id=?',(student_id,)).fetchone()
    if not s: abort(404)
    try:
        from reportlab.lib.pagesizes import landscape
        from reportlab.pdfgen import canvas
        from reportlab.lib import colors
        from reportlab.lib.utils import ImageReader
        from io import BytesIO
        buffer=BytesIO(); w,h=landscape((3.375*72,2.125*72)); p=canvas.Canvas(buffer,pagesize=(w,h))
        st=settings(); p.setFillColor(colors.HexColor(st.get('primary_color','#17365d'))); p.rect(0,h-38,w,38,fill=1,stroke=0)
        p.setFillColor(colors.white); p.setFont('Helvetica-Bold',10); p.drawString(10,h-23,st.get('academy_name','GCA COACHING ACADEMY')[:36])
        p.setFillColor(colors.HexColor('#d7a83e')); p.rect(0,0,5,h,fill=1,stroke=0)
        if s['photo']:
            img=BASE/'static'/'uploads'/s['photo']
            if img.exists():
                try: p.drawImage(str(img),w-74,h-112,width=60,height=68,preserveAspectRatio=True,anchor='c',mask='auto')
                except Exception: pass
        p.setFillColor(colors.HexColor('#17365d')); p.setFont('Helvetica-Bold',9); p.drawString(12,h-54,'STUDENT ID CARD')
        p.setFillColor(colors.black); p.setFont('Helvetica',8)
        rows=[('Name',s['name']),('ID',s['student_code']),('Class',s['class_name']),('Father',s['father'] or '-'),('Mobile',s['phone']),('Admission',s['admission_date'] or '-')]
        y=h-70
        for label,val in rows:
            p.setFont('Helvetica-Bold',7); p.drawString(12,y,label+':'); p.setFont('Helvetica',7); p.drawString(56,y,str(val)[:38]); y-=12
        p.setFont('Helvetica',5.5); p.setFillColor(colors.grey); p.drawString(12,7,st.get('address','')[:85]); p.showPage(); p.save(); buffer.seek(0)
        return send_file(buffer,as_attachment=True,download_name=f'{s["student_code"]}_ID_Card.pdf',mimetype='application/pdf')
    except ImportError: flash('PDF library missing. Run pip install -r requirements.txt','error'); return redirect(url_for('admission_success',student_id=student_id))

@app.route('/learning')
def learning():
    class_name=request.args.get('class_name','')
    with db() as c:
        if class_name: rows=c.execute('SELECT * FROM resources WHERE class_name=? OR class_name="All" ORDER BY id DESC',(class_name,)).fetchall()
        else: rows=c.execute('SELECT * FROM resources ORDER BY id DESC').fetchall()
    return render_template('learning.html',resources=rows,selected_class=class_name)

@app.route('/online-classes')
def online_classes():
    with db() as c: rows=c.execute('SELECT * FROM resources WHERE category="Online Class" ORDER BY id DESC').fetchall()
    return render_template('online_classes.html',classes=rows)

@app.route('/exams')
def exams():
    with db() as c: rows=c.execute('SELECT * FROM exams ORDER BY exam_date DESC').fetchall()
    return render_template('exams.html',exams=rows)

@app.route('/gallery')
def public_gallery():
    with db() as c: rows=c.execute('SELECT * FROM gallery ORDER BY id DESC').fetchall()
    return render_template('gallery.html',gallery=rows)

@app.route('/mcq', methods=['GET','POST'])
def mcq():
    class_name=request.values.get('class_name','10'); subject=request.values.get('subject','')
    with db() as c:
        query='SELECT * FROM questions WHERE class_name=?'; args=[class_name]
        if subject: query+=' AND subject=?'; args.append(subject)
        qs=c.execute(query+' ORDER BY RANDOM() LIMIT 20',args).fetchall()
        subjects=c.execute('SELECT DISTINCT subject FROM questions WHERE class_name=? ORDER BY subject',(class_name,)).fetchall()
    if request.method=='POST':
        name=request.form.get('student_name','Guest').strip() or 'Guest'; ids=request.form.getlist('question_id'); score=0
        with db() as c:
            for qid in ids:
                q=c.execute('SELECT answer FROM questions WHERE id=?',(qid,)).fetchone()
                if q and request.form.get('q_'+qid,'').strip().lower()==str(q['answer']).strip().lower(): score+=1
            c.execute('INSERT INTO mcq_results(student_name,class_name,score,total,attempted_at) VALUES(?,?,?,?,?)',(name,class_name,score,len(ids),datetime.now().isoformat(timespec='seconds')))
        return render_template('mcq_result.html',score=score,total=len(ids),student_name=name)
    return render_template('mcq.html',questions=qs,class_name=class_name,subject=subject,subjects=subjects)

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method=='POST':
        with db() as c: row=c.execute('SELECT value FROM settings WHERE key="admin_password_hash"').fetchone()
        if row and check_password_hash(row['value'],request.form.get('password','')):
            session['admin']=True; return redirect(request.args.get('next') or url_for('admin_dashboard'))
        flash('Incorrect password.','error')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout(): session.clear(); return redirect(url_for('home'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    with db() as c:
        counts={t:c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ['students','resources','exams','payments','attendance','questions','gallery']}
        students=c.execute('SELECT * FROM students ORDER BY id DESC LIMIT 10').fetchall()
        payments=c.execute('SELECT p.*,s.name,s.student_code FROM payments p LEFT JOIN students s ON s.id=p.student_id ORDER BY p.id DESC LIMIT 8').fetchall()
        results=c.execute('SELECT * FROM mcq_results ORDER BY id DESC LIMIT 8').fetchall()
    return render_template('admin_dashboard.html',counts=counts,students=students,payments=payments,results=results)

@app.route('/admin/students')
@admin_required
def admin_students():
    cls=request.args.get('class_name',''); q=request.args.get('q','')
    with db() as c:
        sql='SELECT * FROM students WHERE 1=1'; args=[]
        if cls: sql+=' AND class_name=?'; args.append(cls)
        if q: sql+=' AND (name LIKE ? OR student_code LIKE ? OR phone LIKE ?)'; args += [f'%{q}%']*3
        rows=c.execute(sql+' ORDER BY id DESC',args).fetchall()
    return render_template('admin_students.html',students=rows,selected_class=cls,q=q)

@app.route('/admin/resources', methods=['GET','POST'])
@admin_required
def admin_resources():
    if request.method=='POST':
        f=request.form
        try: path=save_upload(request.files.get('file'),'videos' if f.get('category')=='Video' else 'notes')
        except ValueError as e: flash(str(e),'error'); return redirect(url_for('admin_resources'))
        with db() as c: c.execute('INSERT INTO resources(title,category,class_name,description,file_path,external_url,created_at) VALUES(?,?,?,?,?,?,?)',(f['title'],f['category'],f.get('class_name','All'),f.get('description',''),path,f.get('external_url',''),datetime.now().isoformat(timespec='seconds')))
        flash('Learning resource saved.','success'); return redirect(url_for('admin_resources'))
    with db() as c: rows=c.execute('SELECT * FROM resources ORDER BY id DESC').fetchall()
    return render_template('admin_resources.html',resources=rows)

@app.route('/admin/resources/<int:item_id>/delete',methods=['POST'])
@admin_required
def delete_resource(item_id):
    with db() as c: c.execute('DELETE FROM resources WHERE id=?',(item_id,))
    flash('Resource deleted.','success'); return redirect(url_for('admin_resources'))

@app.route('/admin/exams',methods=['GET','POST'])
@admin_required
def admin_exams():
    if request.method=='POST':
        f=request.form
        with db() as c: c.execute('INSERT INTO exams(title,class_name,exam_date,total_marks,details) VALUES(?,?,?,?,?)',(f['title'],f['class_name'],f.get('exam_date',''),int(f.get('total_marks') or 100),f.get('details','')))
        flash('Exam added.','success'); return redirect(url_for('admin_exams'))
    with db() as c: rows=c.execute('SELECT * FROM exams ORDER BY exam_date DESC').fetchall()
    return render_template('admin_exams.html',exams=rows)

@app.route('/admin/payments',methods=['GET','POST'])
@admin_required
def admin_payments():
    if request.method=='POST':
        f=request.form
        with db() as c: c.execute('INSERT INTO payments(student_id,amount,paid_on,method,reference,note) VALUES(?,?,?,?,?,?)',(int(f['student_id']),float(f['amount']),f.get('paid_on') or date.today().isoformat(),f.get('method','Cash'),f.get('reference',''),f.get('note','')))
        flash('Payment recorded.','success'); return redirect(url_for('admin_payments'))
    with db() as c:
        students=c.execute('SELECT id,name,student_code,class_name FROM students ORDER BY name').fetchall()
        rows=c.execute('SELECT p.*,s.name,s.student_code FROM payments p LEFT JOIN students s ON s.id=p.student_id ORDER BY p.id DESC').fetchall()
    return render_template('admin_payments.html',students=students,payments=rows)

@app.route('/admin/attendance',methods=['GET','POST'])
@admin_required
def admin_attendance():
    cls=request.values.get('class_name','10'); day=request.values.get('class_date',date.today().isoformat())
    with db() as c:
        if request.method=='POST':
            for s in c.execute('SELECT id FROM students WHERE class_name=?',(cls,)).fetchall():
                status=request.form.get('student_'+str(s['id']),'Absent')
                c.execute('INSERT INTO attendance(student_id,class_date,status,note) VALUES(?,?,?,?) ON CONFLICT(student_id,class_date) DO UPDATE SET status=excluded.status,note=excluded.note',(s['id'],day,status,''))
            flash('Attendance saved.','success'); return redirect(url_for('admin_attendance',class_name=cls,class_date=day))
        students=c.execute('SELECT s.*,a.status FROM students s LEFT JOIN attendance a ON a.student_id=s.id AND a.class_date=? WHERE s.class_name=? ORDER BY s.name',(day,cls)).fetchall()
    return render_template('admin_attendance.html',students=students,selected_class=cls,class_date=day)

@app.route('/admin/questions',methods=['GET','POST'])
@admin_required
def admin_questions():
    if request.method=='POST':
        f=request.form
        if request.files.get('question_file') and request.files['question_file'].filename:
            try: path=save_upload(request.files['question_file'],'questions')
            except ValueError as e: flash(str(e),'error'); return redirect(url_for('admin_questions'))
            with db() as c: c.execute('INSERT INTO resources(title,category,class_name,description,file_path,created_at) VALUES(?,?,?,?,?,?)',(f.get('file_title','Question Bank'), 'Question Bank', f.get('class_name','All'),f.get('description',''),path,datetime.now().isoformat(timespec='seconds')))
            flash('Question bank file uploaded as a learning resource.','success'); return redirect(url_for('admin_questions'))
        with db() as c: c.execute('INSERT INTO questions(class_name,subject,chapter,question,a,b,c,d,answer,explanation) VALUES(?,?,?,?,?,?,?,?,?,?)',(f['class_name'],f['subject'],f.get('chapter',''),f['question'],f['a'],f['b'],f['c'],f['d'],f['answer'],f.get('explanation','')))
        flash('MCQ question added.','success'); return redirect(url_for('admin_questions'))
    with db() as c:
        rows=c.execute('SELECT * FROM questions ORDER BY id DESC LIMIT 100').fetchall()
        results=c.execute('SELECT * FROM mcq_results ORDER BY id DESC LIMIT 20').fetchall()
    return render_template('admin_questions.html',questions=rows,results=results)

@app.route('/admin/gallery',methods=['GET','POST'])
@admin_required
def admin_gallery():
    if request.method=='POST':
        f=request.form
        try: path=save_upload(request.files.get('image'),'gallery')
        except ValueError as e: flash(str(e),'error'); return redirect(url_for('admin_gallery'))
        if not path: flash('Choose an image.','error'); return redirect(url_for('admin_gallery'))
        with db() as c: c.execute('INSERT INTO gallery(title,image_path,caption,created_at) VALUES(?,?,?,?)',(f.get('title','Academy Gallery'),path,f.get('caption',''),datetime.now().isoformat(timespec='seconds')))
        flash('Gallery image added.','success'); return redirect(url_for('admin_gallery'))
    with db() as c: rows=c.execute('SELECT * FROM gallery ORDER BY id DESC').fetchall()
    return render_template('admin_gallery.html',gallery=rows)

@app.route('/admin/settings',methods=['GET','POST'])
@admin_required
def admin_settings():
    if request.method=='POST':
        f=request.form
        for key in ['academy_name','tagline','address','phone','email','hero_title','hero_text','primary_color','accent_color','footer_text']:
            save_setting(key,f.get(key,''))
        try:
            logo=save_upload(request.files.get('logo'),'site')
            if logo: save_setting('logo',logo)
            bg=save_upload(request.files.get('background'),'site')
            if bg: save_setting('background',bg)
        except ValueError as e: flash(str(e),'error'); return redirect(url_for('admin_settings'))
        if f.get('new_password'):
            if len(f['new_password'])<10: flash('New admin password must be at least 10 characters.','error'); return redirect(url_for('admin_settings'))
            save_setting('admin_password_hash',generate_password_hash(f['new_password']))
        flash('Website settings saved.','success'); return redirect(url_for('admin_settings'))
    return render_template('admin_settings.html',values=settings())

@app.route('/admin/student/<int:student_id>/delete',methods=['POST'])
@admin_required
def delete_student(student_id):
    with db() as c:
        c.execute('DELETE FROM attendance WHERE student_id=?',(student_id,)); c.execute('DELETE FROM payments WHERE student_id=?',(student_id,)); c.execute('DELETE FROM students WHERE id=?',(student_id,))
    flash('Student record deleted.','success'); return redirect(url_for('admin_students'))

@app.route('/robots.txt')
def robots(): return 'User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /admin/\nSitemap: '+request.url_root.rstrip('/')+'/sitemap.xml\n',200,{'Content-Type':'text/plain'}

@app.route('/sitemap.xml')
def sitemap():
    urls=['','admission','learning','online-classes','exams','gallery','mcq']
    body='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{request.url_root.rstrip("/")}/{u}</loc></url>' for u in urls)+'</urlset>'
    return body,200,{'Content-Type':'application/xml'}


def sync_student_to_google_sheet(student_id):
    """Optional Google Sheets sync. Configure GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID.
    Google API credentials must be private environment variables / secret files, never committed to Git.
    """
    cred=os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON'); sheet_id=os.environ.get('GOOGLE_SHEET_ID')
    if not cred or not sheet_id: return False
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        info=json.loads(cred); scopes=['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/drive.file']
        client=gspread.authorize(Credentials.from_service_account_info(info,scopes=scopes)); sheet=client.open_by_key(sheet_id).sheet1
        with db() as c: s=c.execute('SELECT student_code,name,father,mother,dob,gender,phone,email,address,class_name,course,admission_date FROM students WHERE id=?',(student_id,)).fetchone()
        if s: sheet.append_row([s[k] or '' for k in s.keys()],value_input_option='USER_ENTERED')
        return True
    except Exception as exc:
        app.logger.exception('Google Sheets sync failed: %s',exc); return False

init_db()
if __name__=='__main__': app.run(debug=os.environ.get('FLASK_DEBUG')=='1',host='0.0.0.0',port=int(os.environ.get('PORT',5000)))
