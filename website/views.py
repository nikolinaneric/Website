import secrets
import os
from PIL import Image
from flask import render_template, request, flash, redirect, url_for, current_app, abort
from flask_login import login_required, current_user, login_user, logout_user
from .models import db
from .models import User, Note, UserInfo, DogInfo
from werkzeug.security import generate_password_hash, check_password_hash
from .user_form import UserFormSignUp, UserFormLogIn, UserSetUp, RequestResetForm, ResetPasswordForm, PostForm
from flask_mail import Message, Mail
from . import mail, session, engine
from sqlalchemy import insert, update, join, select, and_, case, text, or_, func

   

@login_required
def home():

    posts = Note.query.all()
    per_page = 10
    current_page = int(request.args.get('page', 1))
    total_pages = (len(posts) + per_page - 1) // per_page
    posts= posts[(current_page - 1) * per_page:current_page * per_page]

    return render_template("home.html", user = current_user, posts = posts, currentPage=current_page, totalPages=total_pages)
    #return render_template("show_all.html", user = current_user, users = UserInfo.query.all())

def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = UserFormLogIn()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data

        user = User.query.filter_by(email=email).first()
        if user:
            if check_password_hash(user.password, password):
                flash('Logged in successfully!', category = 'success') 
                login_user(user, remember = True) 
                next_page = request.args.get('next')  # ako je neulogovan korisnik pokusao pristupiti nekoj stranici ona postaje next nakon logina
                return redirect(next_page) if next_page else redirect(url_for('home'))
                
            else:
                flash('Incorrect password, try again', category = 'error')
        else:
            flash('Email does not exist.', category = 'error')
         
    else:
        print(form.errors)
    return render_template("login.html", user = current_user, form = form)

@login_required    
def logout():
    logout_user()
    return redirect(url_for('login'))

def sign_up():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = UserFormSignUp()
    if form.validate_on_submit():
        email = form.data['email']
        first_name = form.data['first_name']
        password1 = form.data['password1']
        password2 = form.data['password2']
        image_file = 'default.jpg'
    
        new_user = User(email = email, first_name = first_name, password = generate_password_hash(password1, method = 'sha256'), image_file = image_file)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user, remember=True)
        flash('Account created!', category='success')
        return redirect(url_for('set_profile'))

    return render_template("sign_up.html", user = current_user, form = form)

def show_all():
   return render_template('show_all.html', user = current_user, users = User.query.all())

def welcome():
    return render_template('welcome.html')

def save_picture(form_picture):
    random_hex = secrets.token_hex(8)  # za naziv slike u bazi kako ne bi doslo do overrajdovanja
    _, f_ext = os.path.splitext(form_picture.filename)  # f_ext je ekstenzija fajla slike iz forme (npr jpg ili png)
    picture_name = random_hex + f_ext
    picture_path = os.path.join(current_app.root_path,'static/profile_pics/', picture_name)  # napravljen path za cuvanje slike

    # smanjivanje velicine slike radi ustede memorije u bazi pomocu pillow paketa:

    output_size = (900,450)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)   # cuvanje slike na picture_pathu

    return picture_name


@login_required
def set_profile():
    form = UserSetUp()
    image_file = url_for('static', filename='profile_pics/' + current_user.image_file)
    if form.validate_on_submit():
        if form.data['picture']:
            profile_pic = save_picture(form.picture.data)
            previous_pic = current_user.image_file
            if previous_pic != "default.jpg":
                os.remove(current_app.root_path + '/static/profile_pics/' + previous_pic)
            current_user.image_file = profile_pic
        current_user.email = form.data['email']
        current_user.first_name = form.data['first_name']
        db.session.commit()
        flash('Your account has been updated!', 'success')
        return redirect(url_for('set_profile'))

    elif request.method == 'GET':
        form.first_name.data = current_user.first_name
        form.email.data = current_user.email
        
    return render_template('set_profile.html', user = current_user, form= form, image_file = image_file)

def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        send_reset_email(user)
        flash('An email has been sent with instructions to reset your password.', 'info')
        return redirect(url_for('login'))
   
    return render_template('reset_request.html', form = form, user = current_user)

def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request',
                  sender='noreply@demo.com',
                  recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link:
{url_for('reset_token', token=token, _external=True)}  
If you did not make this request then simply ignore this email and no changes will be made.
'''
    mail.send(msg)
    #external = True znaci da se salje apsolutno url kao npr https://example.com/my-page, a ne relativni -/mypage

def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    user = User.verify_reset_token(token)  # vracamo nam odgovarajuci user objekat na osnovu id iz tokena
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password1.data, method = 'sha256')
        user.password = hashed_password
        db.session.commit()
        flash('Your password has been updated! You are now able to log in', 'success')
        return redirect(url_for('login'))
    else:
        print(form.errors)
    return render_template('reset_password.html', form=form, user = current_user)

@login_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        photo = form.picture.data
        image_name = save_picture(photo)
        #image_file = url_for('static', filename='profile_pics/' + image_name)
        post = Note(title=form.title.data, data=form.data.data, user_id = current_user.id, image_file = image_name)
        db.session.add(post)
        db.session.commit()
    
        response = request.form
        dog_data = {
        "primary_breed" : (response.get('a1')).lower(),
        "mixed_breed" : bool(int(response.get('a2'))),
        "age" : response.get('a3'),
        "size" : response.get('a4'),
        "color" : response.get('a5'),
        "spayed" : bool(int(response.get('a6'))) ,
        "coat_length" : response.get('a7'),
        "dog_with_children" : bool(int(response.get('a8'))) if response.get('a8') else 'unknown',
        "dog_with_dogs" : bool(int(response.get('a9'))) if response.get('a9') else 'unknown',
        "dog_with_cats" : bool(int(response.get('a10'))) if response.get('a10') else 'unknown',
        "dog_with_sm_animals" : bool(int(response.get('a11'))) if response.get('a11') else 'unknown',
        "dog_with_big_animals" : bool(int(response.get('a12'))) if response.get('a12') else 'unknown',
        "activity_level" : response.get('a13'),
        "special_need_dog" : bool(int(response.get('a14'))),
        "note_id": post.id
        }

        dog = DogInfo(**dog_data)
        db.session.add(dog)
        db.session.commit()

        print(dog.primary_breed, dog.activity_level, dog.dog_with_cats, 'cats')

        return redirect(url_for('home'))
    return render_template('new_post.html', user = current_user, form = form, title ="Create a new post")

def post(post_id):
    post = Note.query.get_or_404(post_id)
    return render_template('post.html', title=post.title, post=post, user = current_user)

@login_required
def update_post(post_id):
    post = Note.query.get_or_404(post_id)
    print(f"{post.user_id} - {current_user.id}")
    if post.user_id != current_user.id:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post.title = form.title.data
        post.data = form.data.data
        db.session.add(post)
        db.session.commit()
        flash('Your post has been updated!', 'success')

        response = request.form
        dog_update_data = {
        "primary_breed" : (response.get('a1')).lower(),
        "mixed_breed" : bool(int(response.get('a2'))) if response.get('a2') else '',
        "age" : response.get('a3'),
        "size" : response.get('a4'),
        "color" : response.get('a5'),
        "spayed" : bool(int(response.get('a6'))) if response.get('a6') else '',
        "coat_length" : response.get('a7'),
        "dog_with_children" : bool(int(response.get('a8'))) if response.get('a8') else '',
        "dog_with_dogs" : bool(int(response.get('a9'))) if response.get('a9') else '',
        "dog_with_cats" : bool(int(response.get('a10'))) if response.get('a10') else '',
        "dog_with_sm_animals" : bool(int(response.get('a11'))) if response.get('a11') else '',
        "dog_with_big_animals" : bool(int(response.get('a12'))) if response.get('a12') else '',
        "activity_level" : response.get('a13'),
        "special_need_dog" : bool(int(response.get('a14')))if response.get('a14') else '',
        "note_id": post.id
        }
        dog_update_data = {k: v for k, v in dog_update_data.items() if v}
        print(post.id)


        # sql = text("UPDATE dog_info SET dog_with_cats = :dog_with_cats WHERE note_id = :note_id")

        # conn = engine.connect()
        # conn.execute(sql, dog_with_cats = bool(int(response.get('a10'))) if response.get('a10') else '', note_id=post.id)

        doggo_info = DogInfo.query.filter_by(note_id=post.id)
        doggo_info = db.session.query(DogInfo).filter(DogInfo.note_id==post.id)
        print(doggo_info.update(dog_update_data),'update')
        print(doggo_info.first().dog_with_cats, 'macke',)
        db.session.commit()
        print(doggo_info.first().dog_with_cats, 'macke')
        dog = DogInfo.query.filter_by(note_id = post.id).first()
        print(dog.primary_breed, dog.activity_level, dog.dog_with_cats,dog.dog_with_sm_animals, "small an")



        return redirect(url_for('post', post_id = post.id, user = current_user))
    elif request.method == 'GET':
        form.title.data = post.title
        form.data.data = post.data
    return render_template('new_post.html', title='Update Post',
                           form=form, legend = "Update post", user = current_user)


@login_required
def delete_post(post_id):
    post = Note.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash('Your post has been deleted!', 'success')
    return redirect(url_for('home'))

def user_info():
    if request.method == 'GET':
        breeds = set()
        for dog in session.query(DogInfo.primary_breed).filter(DogInfo.primary_breed != ('unknown' or 'Unknown')).distinct():
            breeds.add((dog.primary_breed).lower())
        info = UserInfo.query.filter_by(user_id = current_user.id).first()
        if info:
            return redirect(url_for('show_matches'))
    if request.method == 'POST':
        response = request.form
        prefered_breed = response.getlist('q1')
        prefers_mixed_breed = bool(int(response.get('q2')) )
        age_preference = response.getlist('q3') 
        size_preference = response.getlist('q4')
        color_preference = response.getlist('q5')
        spay_needed = bool(int(response.get('q6')))
        coat_length_preference = response.get('q7')
        dog_with_children = bool(int(response.get('q8')))
        dog_with_dogs = bool(int(response.get('q9')))
        dog_with_cats = bool(int(response.get('q10')))
        dog_with_sm_animals = bool(int(response.get('q11')))
        dog_with_big_animals = bool(int(response.get('q12')))
        dog_in_house = bool(int(response.get('q13')))
        yard = bool(int(response.get('q14')))
        park = bool(int(response.get('q15')))
        activity_level = response.get('q16')
        special_need_dog = bool(int(response.get('q17')))
        flash('You successfully submited your answers. Here are your matches!', 'success')
        
        
        info = UserInfo.query.filter_by(user_id = current_user.id).first()
        if info:
            info.prefered_breed = prefered_breed
            info.prefers_mixed_breed = prefers_mixed_breed 
            info.age_preference = age_preference,
            info.size_preference = size_preference 
            info.color_preference = color_preference 
            info.spay_needed = spay_needed 
            info.coat_length_preference = coat_length_preference
            info.dog_with_children = dog_with_children 
            info.dog_with_dogs = dog_with_dogs 
            info.dog_with_cats = dog_with_cats 
            info.dog_with_sm_animals = dog_with_sm_animals 
            info.dog_with_big_animals = dog_with_big_animals 
            info.dog_in_house = dog_in_house 
            info.yard = yard
            info.park = park 
            info.activity_level = activity_level
            info.special_need_dog = special_need_dog 
            info.user_id = current_user.id
        
            db.session.commit()
        else:
            info = UserInfo(prefered_breed = prefered_breed, prefers_mixed_breed = prefers_mixed_breed, age_preference = age_preference,
            size_preference = size_preference, color_preference = color_preference, spay_needed = spay_needed, coat_length_preference = coat_length_preference,
            dog_with_children = dog_with_children, dog_with_dogs = dog_with_dogs, dog_with_cats = dog_with_cats, dog_with_sm_animals = dog_with_sm_animals, 
            dog_with_big_animals = dog_with_big_animals, dog_in_house = dog_in_house, yard = yard, park = park, 
            activity_level = activity_level, special_need_dog = special_need_dog, user_id = current_user.id)
            db.session.add(info)
            db.session.commit()
        print(info.prefered_breed)

        return redirect(url_for('show_matches') )

    return render_template('user_info.html', user = current_user, breeds = breeds)

@login_required
def show_matches():
    with session:
 
        prefered_breeds = (session.query(UserInfo.prefered_breed).filter(UserInfo.user_id == current_user.id).all())[0][0]
        age_preference = (session.query(UserInfo.age_preference).filter(UserInfo.user_id == current_user.id).all())[0][0][0]
        size_preference = (session.query(UserInfo.size_preference).filter(UserInfo.user_id == current_user.id).all())[0][0]
        color_preference = (session.query(UserInfo.color_preference).filter(UserInfo.user_id == current_user.id).all())[0][0]
        coat_length_preference = (session.query(UserInfo.coat_length_preference).filter(UserInfo.user_id == current_user.id).all())[0]


        result = db.session.query(Note, DogInfo, UserInfo).join(DogInfo, Note.id == DogInfo.note_id)\
                .join(UserInfo, UserInfo.user_id == current_user.id, isouter=True)\
                .filter( UserInfo.user_id == current_user.id)\
                .filter(case([('all' not in age_preference, DogInfo.age.in_(age_preference)),], else_= True))\
                .filter(case([('all' not in prefered_breeds, DogInfo.primary_breed.in_(prefered_breeds)),], else_= True))\
                .filter(case([(UserInfo.prefers_mixed_breed == False, DogInfo.mixed_breed == UserInfo.prefers_mixed_breed),], else_= True))\
                .filter(case([('all' not in size_preference, DogInfo.size.in_(size_preference)),], else_= True))\
                .filter(case([('all' not in color_preference, DogInfo.color.in_(color_preference)),], else_= True))\
                .filter(case([('all' not in coat_length_preference, DogInfo.coat_length.in_(coat_length_preference)),], else_= True))\
                .filter(case([(UserInfo.dog_with_children == True, UserInfo.dog_with_children == DogInfo.dog_with_children),], else_= True))\
                .filter(case([(UserInfo.dog_with_dogs == True, UserInfo.dog_with_dogs == DogInfo.dog_with_dogs),], else_= True))\
                .filter(case([(UserInfo.dog_with_cats == True, UserInfo.dog_with_cats == DogInfo.dog_with_cats),], else_= True))\
                .filter(case([(UserInfo.dog_with_sm_animals == True, UserInfo.dog_with_sm_animals == DogInfo.dog_with_sm_animals),], else_= True))\
                .filter(case([(UserInfo.dog_with_big_animals == True, UserInfo.dog_with_big_animals == DogInfo.dog_with_big_animals),], else_= True))\
                .filter(case([(UserInfo.special_need_dog == False, UserInfo.special_need_dog == DogInfo.special_need_dog),], else_= True))\
                .filter(case([(UserInfo.spay_needed == True, UserInfo.spay_needed == DogInfo.spayed),], else_= True))\
                .filter(case([(UserInfo.dog_in_house == False,and_(DogInfo.age != "puppy", DogInfo.size != 'small')),], else_= True))\
                .filter(case([(or_(UserInfo.yard == True , UserInfo.park == True), DogInfo.activity_level == UserInfo.activity_level),\
                   (and_(UserInfo.yard == False , UserInfo.park == False, UserInfo.activity_level == 'high'), DogInfo.activity_level != 'high'),\
                    (and_(UserInfo.yard == False , UserInfo.park == False, UserInfo.activity_level != 'high'), UserInfo.activity_level == DogInfo.activity_level),], else_= True))\
                
        if not result:
            flash('Oops, it seems there aren\'t matches for your preferences...', category='error')
            warning = "Check if there are preferences that can be modified or take a look at some of the our random choices."
        else:
            result, warning = result.filter(case([(and_(UserInfo.dog_in_house == False, UserInfo.yard == False), False)], else_=True)).all(), None
            if result == []:
                warning = "If you would not keep a dog in the house and if there is no yard, then where would the dog live?\
                Please check your answers."
            flash('Oops, it seems there aren\'t matches for your preferences...', category='error')
        for res in result:
            print(res)
        alternative_results = db.session.query(Note, DogInfo, UserInfo).join(DogInfo, Note.id == DogInfo.note_id)\
                .join(UserInfo, UserInfo.user_id == current_user.id, isouter=True)\
                .filter( UserInfo.user_id == current_user.id).order_by(func.random()).limit(8).all()
        per_page = 10
        current_page = int(request.args.get('page', 1))
    #total_pages = (len(posts) + per_page - 1) // per_page
    # posts= posts[(current_page - 1) * per_page:current_page * per_page]

        return render_template('show_matches.html', alternative_posts = alternative_results,warning = warning ,user = current_user, posts = result, currentPage=current_page, totalPages=10 )


