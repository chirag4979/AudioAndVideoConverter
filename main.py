from flask import Flask, request, render_template, send_from_directory
from flask_socketio import SocketIO, emit
from loggers import *
from werkzeug.utils import secure_filename
import logging, os
import converter
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from confidential import *
import urllib # For YT downloader.
from bs4 import BeautifulSoup # For YT downloader.

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['MAX_CONTENT_LENGTH'] = 5 * 1000 * 1000 * 1000 # 5 GB max upload size.
app.jinja_env.auto_reload = True

socketio = SocketIO(app) # Turn the flask app into a SocketIO app.

@app.route("/")
def homepage_visited():
    log_visit("visited homepage")
    return render_template("home.html", title="FreeAudioConverter.net")

@app.route("/about")
def about_page_visited():
    log_visit("visited about page")
    return render_template("about.html", title="About")

@app.route("/filetypes")
def filetypes_visited():
    log_visit("visited filetypes")
    return render_template("filetypes.html", title="Filetypes")

@app.route("/yt")
def yt_page_visited():
    log_visit("visited YT")
    return render_template("yt.html")

@app.route("/file-trimmer")
def trimmer_visited():
    log_visit("visited trimmer")
    return render_template("trimmer.html", title="File Trimmer")

@app.route("/contact")
def contact_page_visited():
    log_visit("visited contact page")
    return render_template("contact.html", title="Contact")

@app.route("/game")
def game_visited():
    log_visit("visited game")  
    return render_template("game.html", title="Game")

@app.route("/game2")
def game2_visited():
    log_visit("visited game 2")  
    return render_template("game2.html", title="Game 2")

# FFmpeg will write the conversion progress to a txt file. Read the file every second to get the
# current conversion progress every second.
def read_progress():
    previous_time = '00:00:00'
    while True:
        with open('progress.txt', 'r') as f:
            lines = f.readlines()
            # This gives us the amount of the file that has been converted so far.
            current_time = lines[-5].split('=')[-1]
            # FFmpeg also shows the encoding speed.
            speed = lines[-2].split('=')[-1]
            # If the amount converted is the same twice in a row, that means that the conversion is complete.
            if previous_time == current_time:
                log.info(f'File Length: {current_time}')
                break
            hh_mm_ss = current_time.split('.')[0]
            milliseconds = current_time.split('.')[-1][:-4]
            progress_message = f'{hh_mm_ss} [HH:MM:SS] of the file has been converted so far...<br>'
            f'(and {milliseconds} millseconds)<br>Encoding Speed: {speed}'
            # Trigger a new event called "show progress" 
            socketio.emit('show progress', {'progress': progress_message})
            socketio.sleep(1)
            # Set the value of previous_time to current_time, so we can check if the value of previous_time is
            # the same as the value of current_time in the next iteration of the loop.
            previous_time = current_time

# When a file has been uploaded, a POST request is sent to the homepage.
@app.route("/", methods=["POST"])
def homepage():
    if request.form["request_type"] == "uploaded":

        chosen_file = request.files["chosen_file"]
        filesize = request.form["filesize"]
        log_this('uploaded a file:')
        log.info(chosen_file)
        log.info(f'Size: {filesize} MB')
        # Make the filename safe
        filename_secure = secure_filename(chosen_file.filename)
        # Save the uploaded file to the uploads folder.
        chosen_file.save(os.path.join("uploads", filename_secure))
        return '' # Something has to be returned, so I'm returning an empty string.

    elif request.form["request_type"] == "convert":

        wav_bit_depth = request.form["wav_bit_depth"]
        filename = request.form["filename"]
        filename_without_ext = filename.split('.')[0]
        chosen_codec = request.form["chosen_codec"]
        crf_value = request.form["crf_value"]
        mp4_encoding_mode = request.form["mp4_encoding_mode"]
        is_keep_video = request.form["is_keep_video"]
        uploaded_file_path = os.path.join("uploads", secure_filename(filename))
        # MP3
        mp3_encoding_type = request.form["mp3_encoding_type"]
        mp3_bitrate = request.form["mp3_bitrate"]
        mp3_vbr_setting = request.form["mp3_vbr_setting"]
        # AAC
        fdk_type = request.form["fdk_type"]
        fdk_cbr = request.form["fdk_cbr"]
        fdk_vbr = request.form["fdk_vbr"]
        is_fdk_lowpass = request.form["is_fdk_lowpass"]
        fdk_lowpass = request.form["fdk_lowpass"]
        # Vorbis
        vorbis_encoding = request.form["vorbis_encoding"]
        vorbis_quality = request.form["vorbis_quality"]
        # Vorbis/Opus
        opus_vorbis_slider = request.form["opus_vorbis_slider"]
        # AC3 
        ac3_bitrate = request.form["ac3_bitrate"]
        # FLAC
        flac_compression = request.form["flac_compression"]
        # DTS
        dts_bitrate = request.form["dts_bitrate"]
        # Opus
        opus_cbr_bitrate = request.form["opus_cbr_bitrate"]
        opus_encoding_type = request.form["opus_encoding_type"]
        # Desired filename
        output_name = request.form["output_name"]

        variables_to_validate = [filename_without_ext, chosen_codec, is_keep_video, mp3_encoding_type, mp3_bitrate,
        mp3_vbr_setting, fdk_type, fdk_cbr, fdk_vbr, is_fdk_lowpass, vorbis_encoding, vorbis_quality,
        opus_vorbis_slider, ac3_bitrate, flac_compression, dts_bitrate, opus_cbr_bitrate, opus_encoding_type,
        output_name, wav_bit_depth, mp4_encoding_mode, crf_value]

        strings_not_allowed = ['command', ';', '$', '&&', '/', '\\' '"', '?', '*', '<', '>', '|', ':', '`', '.']

        # check_no_variable_contains_bad_string is a func defined in converter.py
        if not converter.check_no_variable_contains_bad_string(variables_to_validate, strings_not_allowed):
            return {"message": "You tried being clever, but there's a server-side check for disallowed strings."}, 400

        else:
            log.info(f'They chose {chosen_codec}\nOutput Filename: {output_name}')
            output_path = f'"conversions/{output_name}"'
            # Start the read_progress function in a new thread.
            socketio.start_background_task(read_progress)

            # Run the appropritate section of converter.py:

            if chosen_codec == 'MP3':
                converter.run_mp3(uploaded_file_path, mp3_encoding_type, mp3_bitrate, mp3_vbr_setting, output_path)
                extension = 'mp3'

            elif chosen_codec == 'AAC':
                converter.run_aac(uploaded_file_path, is_keep_video, fdk_type, fdk_cbr, fdk_vbr, is_fdk_lowpass,
                fdk_lowpass, output_path)
                if is_keep_video == "yes":
                    just_ext = uploaded_file_path.split('.')[-1]
                    if just_ext == 'mp4':
                        extension = 'mp4'
                    else:
                        extension = 'mkv'
                else:
                    extension = 'm4a'

            elif chosen_codec == 'Opus':
                converter.run_opus(uploaded_file_path, opus_encoding_type, opus_vorbis_slider, opus_cbr_bitrate,
                output_path)
                extension = 'opus'   

            elif chosen_codec == 'FLAC':
                converter.run_flac(uploaded_file_path, is_keep_video, flac_compression, output_path)
                if is_keep_video == "yes":
                    extension = 'mkv'
                else:
                    extension = 'flac'

            elif chosen_codec == 'Vorbis':
                converter.run_vorbis(uploaded_file_path, vorbis_encoding, vorbis_quality, opus_vorbis_slider,
                output_path) 
                extension = 'mka'

            elif chosen_codec == 'WAV':
                converter.run_wav(uploaded_file_path, is_keep_video, wav_bit_depth, output_path)
                if is_keep_video == "yes":
                    extension = 'mkv'
                else:
                    extension = 'wav'

            elif chosen_codec == 'MKV':
                converter.run_mkv(uploaded_file_path, output_path)
                extension = 'mkv'

            elif chosen_codec == 'MKA':
                converter.run_mka(uploaded_file_path, output_path)
                extension = 'mka'

            elif chosen_codec == 'ALAC':
                converter.run_alac(uploaded_file_path, is_keep_video, output_path)
                if is_keep_video == "yes":
                    extension = 'mkv'
                else:
                    extension = 'm4a'

            elif chosen_codec == 'AC3':
                converter.run_ac3(uploaded_file_path, is_keep_video, ac3_bitrate, output_path)
                if is_keep_video == "yes":
                    just_ext = uploaded_file_path.split('.')[-1]
                    if just_ext == 'mp4':
                        extension = 'mp4'
                    else:
                        extension = 'mkv'
                else:
                    extension = 'ac3'

            elif chosen_codec == 'CAF':
                converter.run_caf(uploaded_file_path, output_path)
                extension = 'caf'

            elif chosen_codec == 'DTS':
                converter.run_dts(uploaded_file_path, is_keep_video, dts_bitrate, output_path)
                if is_keep_video == "yes":
                    extension = 'mkv'
                else:
                    extension = 'dts'

            elif chosen_codec == 'MP4':
                converter.run_mp4(uploaded_file_path, mp4_encoding_mode, crf_value, output_path)
                extension = 'mp4'
            
            elif chosen_codec == 'MKV':
                converter.run_mkv(uploaded_file_path, output_path)
                extension = 'mkv'

            converted_file_name = output_name + "." + extension
            return {
                "message": "File converted.",
                "downloadFilePath": f'/download/{converted_file_name}'
            }

# FILE TRIMMER:
@app.route("/file-trimmer", methods=["POST"])
def trim_file():
    if request.form["request_type"] == "upload_complete":
   
        uploaded_file_path = request.files["uploaded_file_path"]
        # Make the filename safe
        filename_secure = secure_filename(uploaded_file_path.filename)
        # Save the uploaded file to the uploads folder.
        uploaded_file_path.save(os.path.join("uploads", filename_secure))
        return ''

    if request.form["request_type"] == "trim":

        file_name = request.form["filename"]
        uploaded_file_path = os.path.join("uploads", secure_filename(file_name))
        filename = request.form["filename"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]
        ext = "." + filename.split(".")[-1]
        just_name = filename.split(".")[0]
        output_name = just_name + " [trimmed]" + ext

        try:
            os.system(f'/usr/local/bin/ffmpeg -y -i "{uploaded_file_path}" -ss {start_time} '
            f'-to {end_time} -c copy "{output_name}"')
        except Exception as error:
            logger.error(f'TRIMMER: {error}')
        else:
            log.info('Trim complete.')
            return {
                "message": "File trimmed. The trimmed file will now start downloading.",
                "downloadFilePath": f'/download/{output_name}'
            }

# Send the converted/trimmed file to the following URL, where <filename> is the "value" for downloadFilePath
@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    just_extension = filename.split('.')[-1]
    if just_extension == "m4a":
        return send_from_directory(f'{os.getcwd()}/conversions', filename, mimetype="audio/mp4")
    else:
        return send_from_directory(f'{os.getcwd()}/conversions', filename)

# CONTACT PAGE
@app.route("/contact", methods=["POST"])
def send_email():
    send_from = "theaudiophile@outlook.com"
    send_to = "theaudiophile@outlook.com"
    text = MIMEMultipart()
    text['From'] = send_from
    text['To'] = send_to
    text['Subject'] = "Your Website"
    body = request.form['message']
    text.attach(MIMEText(body, 'plain'))
    server = smtplib.SMTP(host='smtp-mail.outlook.com', port=587)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(my_email, password)
    text = text.as_string()
    server.sendmail(send_from, send_to, text)
    return "Message sent!"

# GAME 1
@app.route("/game", methods=['POST'])
def return_world_record():
    current_datetime = (datetime.now() + timedelta(hours=1)).strftime('%d-%m-%y at %H:%M:%S')
    user = request.environ.get("HTTP_X_REAL_IP").split(',')[0]
    user_agent = request.headers.get('User-Agent')
    score = request.form['score']
    times_missed = request.form['times_missed']
    canvas_width = request.form['canvas_width']
    canvas_height = request.form['canvas_height']
    try:
        int(score)
        int(times_missed)
        int(canvas_width)
        int(canvas_width)
    except ValueError:
        logger.error("GAME 1: The user changed something to a non-int.")
    else:
        with open("Game Scores/HighScores.txt", "a") as f:
            f.write(f'{score} | {times_missed} | {user} | {user_agent} | {canvas_width}'
            f'x{canvas_height} | {current_datetime}\n')
    finally:
        just_scores = []
        with open('Game Scores/HighScores.txt', 'r') as f:
            lines = f.readlines()
            for line in lines:
                just_scores.append(line.split('|')[0].strip())

        valid_scores = [x for x in just_scores if int(x) < 100]
        world_record = max(valid_scores, key=lambda x: int(x))
        return world_record

# GAME 2
@app.route("/game2", methods=['POST'])
def save_game2_stats():
    current_datetime = (datetime.now() + timedelta(hours=1)).strftime('%d-%m-%y at %H:%M:%S')
    user = request.environ.get("HTTP_X_REAL_IP").split(',')[0]
    user_agent = request.headers.get('User-Agent')
    reaction_time = request.form['reaction_time']
    try:
        int(reaction_time)
    except ValueError:
        logger.error("GAME 2: The user changed reaction_time to a non-int.")
    else:
        with open("Game Scores/ReactionTimes.txt", "a") as f:
            f.write(f'{reaction_time} ms | {user} | {user_agent} | {current_datetime}\n')
    finally:
        reaction_times = []
        with open('Game Scores/ReactionTimes.txt', 'r') as f:
            lines = f.readlines()
            for line in lines:
                reaction_times.append(line.split('|')[0][:-3].strip())

        # reaction_record = min(reaction_times, key=lambda x: int(x))
        return ''

# YOUTUBE DOWNLOADER:
@app.route("/yt", methods=["POST"])
def yt_downloader():
    media_extensions = ["mp4", "webm", "opus", "mkv", "aac", "m4a", "mp3"]
    strings_not_allowed = ['command', ';', '$', '&&', '\\' '"', '*', '<', '>', '|', '`']
    link = request.form.getlist("link")[0]
    source = urllib.request.urlopen(f'{link}').read()
    soup = BeautifulSoup(source, features="html.parser")
    title = soup.title.string[:-10]

    # check_no_variable_contains_bad_string is a func defined in converter.py
    if not converter.check_no_variable_contains_bad_string(link, strings_not_allowed):
        return {"message": "You tried being clever, but there's a server-side check for disallowed strings."}, 400
    
    # Delete the videos that have already been downloaded so send_from_directory does not send back the wrong file.
    for file in os.listdir():
        if file.split(".")[-1] in media_extensions:
            os.remove(file)
        else:
            pass

    if request.form['submit'] == 'Download Video':

        os.system(f'youtube-dl --newline -o "%(title)s.%(ext)s" {link} | tee static/output.txt')

        with open("downloaded-files.txt", "a") as f:
            f.write("\n" + title + " downloaded.") 
        
        for file in os.listdir():
            if file.split(".")[-1] in media_extensions:
                return send_from_directory(os.getcwd(), file, as_attachment=True)

    elif request.form['submit'] == 'Download Video [iOS]':

        os.system(f'youtube-dl --newline -f mp4 -o "%(title)s.%(ext)s" {link} | tee static/output.txt')

        with open("downloaded-files.txt", "a") as f:
            f.write("\n" + title + " downloaded.") 
        
        for file in os.listdir():
            if file.split(".")[-1] in media_extensions:
                return send_from_directory(os.getcwd(), file, as_attachment=True)

    elif request.form['submit'] == 'Download Audio (best quality)':

        os.system(f'youtube-dl --newline -x -o "%(title)s.%(ext)s" {link} | tee static/output.txt')

        with open("downloaded-files.txt", "a") as f:
            f.write("\n" + title + " downloaded.") 
        
        for file in os.listdir():
            if file.split(".")[-1] in media_extensions:
                return send_from_directory(os.getcwd(), file, as_attachment=True)

    elif request.form['submit'] == 'Download as an MP3 file':

        os.system(f'youtube-dl --newline -x --audio-format mp3 --audio-quality 0 '
        f'--embed-thumbnail -o "%(title)s.%(ext)s" {link} | tee static/output.txt')

        with open("downloaded-files.txt", "a") as f:
            f.write("\n" + title + " downloaded.") 
        
        for file in os.listdir():
            if file.split(".")[-1] in media_extensions:
                return send_from_directory(os.getcwd(), file, as_attachment=True)

if __name__ == "__main__":
    socketio.run(app)