from flask import Flask, request, render_template, send_file, jsonify
from gtts import gTTS
import speech_recognition as sr
import os
from werkzeug.utils import secure_filename
from googletrans import Translator
from pydub import AudioSegment
import uuid
os.environ["PATH"] += os.pathsep + r"C:\ProgramData\chocolatey\bin"
app = Flask(__name__)

# Configuration for uploads
UPLOAD_FOLDER = 'uploads/'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/text-to-voice', methods=['POST'])
def text_to_voice():
    # Text received from front-end  
    text = request.form.get('text', '').strip()
    # Language in which we want to translate the Input text ?
    # target_lang store the Language-code for the desired language ?
    target_lang = request.form.get('language', 'en')  # Default language is English
    if not text:
        return jsonify({"error": "Text input cannot be empty."}), 400
    if len(text) > 5000:
        return jsonify({"error": "Text input exceeds the character limit."}), 400
    try:
        # Detect source language and translate if needed
        translator = Translator()
        detected_lang = translator.detect(text).lang
        text = translator.translate(text, src=detected_lang, dest=target_lang).text
    except Exception as e:
        return jsonify({"error": f"Translation failed: {e}"}), 500
    try:
        # Generate speech ?
        tts = gTTS(text, lang = target_lang)
        audio_file = os.path.join(app.config['UPLOAD_FOLDER'], f'output_{uuid.uuid4().hex}.mp3')
        tts.save(audio_file)
        return send_file(audio_file, as_attachment = True)
    except Exception as e:
        return jsonify({"error": f"Text-to-speech conversion failed: {e}"}), 500 

def convert_audio(input_file, output_format="wav"):
    try:
        sound = AudioSegment.from_file(input_file)
        output_file = input_file.replace(input_file.split('.')[-1], output_format)
        sound.export(output_file, format=output_format)
        return output_file
    except Exception as e:
        raise Exception(f"Audio conversion failed: {e}")
    
AudioSegment.converter = r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"
@app.route('/voice-to-text', methods=['POST'])
def voice_to_text():
    # Check for uploaded file
    if 'audio' not in request.files or request.files['audio'].filename == '':
        return jsonify({"error": "No audio file uploaded."}), 400

    file = request.files['audio']
    if not file.filename.endswith(('.wav', '.mp3')):
        return jsonify({"error": "Invalid file type. Please upload a .wav or .mp3 file."}), 400

    target_lang = request.form.get('language', 'en')  # Target language for translation

    try:
        # Save the uploaded file
        filename = secure_filename(file.filename)
        original_file_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{uuid.uuid4().hex}_{filename}')
        file.save(original_file_path)

        # If the file is MP3, convert it to WAV first
        if original_file_path.endswith('.mp3'):
            file_to_process = convert_audio(original_file_path)
        else:
            file_to_process = original_file_path

        
        recognizer = sr.Recognizer()
        with sr.AudioFile(file_to_process) as source:
            audio = recognizer.record(source)

        # Transcribe audio to text
        try:
            text = recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return jsonify({"error": "Could not understand the audio."}), 400
        except sr.RequestError as e:
            return jsonify({"error": f"Speech recognition API error: {e}"}), 500 

        # Detect the language of the transcribed text
        translator = Translator()
        detected_lang = translator.detect(text).lang
        
        # If the detected language is Hindi, then translate the text to Hindi correctly
        if detected_lang == "en" and target_lang == "hi":
            # Direct translation using googletrans
            translated_text = translator.translate(text, src='en', dest='hi').text
        else:
            # If the detected language is different, translate normally
            translated_text = translator.translate(text, src=detected_lang, dest=target_lang).text

        # Return response in a cleaner format
        response = {
            "status": "success",
            "original_text": text,
            "translated_text": translated_text,
            "detected_language": detected_lang,
            "target_language": target_lang,
        }
        return jsonify(response)

    except Exception as e:
        return jsonify({"error": f"Voice-to-text conversion failed: {e}"}), 500

    finally:
        # Cleanup files
        for file_path in [original_file_path]:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as cleanup_error:
                    print(f"Failed to delete file {file_path}: {cleanup_error}")


if __name__ == "__main__":
    app.run(debug=True)
