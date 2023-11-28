from flask import Flask, request, jsonify
from clustering import relevant_clustering
from similarity import calculate_similarity as calc_sim
from pdfconverter import converttopdf
from llm import llama_supernotes
from ocr import pdf_to_text
import os
import json
import shutil
import firebase_admin
from firebase_admin import credentials, storage

app = Flask(__name__)

def download_blob(source_blob_name, destination_file_name):
    """Downloads a blob from the bucket."""
    bucket = storage.bucket()
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)
    print(f"Downloaded {source_blob_name} to {destination_file_name}.")

# Firebase download
def list_files(prefix, local_folder):
    """Lists and downloads all the files in the bucket that are in the specified folder."""
    bucket = storage.bucket()

    blobs = bucket.list_blobs(prefix=prefix)
    print("printing blobs")
    print("prefix:", prefix)
    for blob in blobs:
        print(blob.name)
        if not blob.name.endswith('/'):  # Skip directories
            local_file_path = local_folder + os.path.basename(blob.name)
            
            if not os.path.exists(local_folder):
                os.makedirs(local_folder)  # Create the directory if it does not exist
            download_blob(blob.name, local_file_path)

def average_file_length(folder_path):
    total_words = 0
    file_count = 0

    for filename in os.listdir(folder_path):
        if filename.endswith(".txt"):
            file_path = os.path.join(folder_path, filename)
            
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                # Count the number of words (assuming words are separated by whitespace)
                words = content.split()
                total_words += len(words)
                file_count += 1

    if file_count == 0:
        return 0  # Avoid division by zero

    average_words = total_words / file_count
    return average_words

# $nameOfClass/$lectureNumber/supernote/filename
# Firebase upload 
def upload_file(destination_path, local_path):
    bucket = storage.bucket()
    blob = bucket.blob(destination_path)
    blob.upload_from_filename(local_path)

bucket_name = 'note-mesh.appspot.com'  # Corrected bucket name
# Local directory to save the files
print("Firebase setup")
cred = credentials.Certificate("key.json")
firebase_admin.initialize_app(cred, {'storageBucket': bucket_name})

def generate_all_txtfiles(path):
    if not os.path.exists('./docs'):
        os.mkdir('./docs')
    if not os.path.exists('./output'):
        os.mkdir('./output')
    list_files(path, "student_notes/notes/ClassName/")
    for each in os.listdir('./student_notes/notes/ClassName'):
        print("each", each)
        filepath = './docs/' + each + '.txt'
        pdf_to_text('./student_notes/notes/ClassName/' + each, filepath)


@app.route("/supernotes", methods=['POST'])
def run_llama_supernotes():
    data = request.json
    # list_files(data["path"], "student_notes/notes/ClassName")
    generate_all_txtfiles(data["path"])
    print("path:", data["path"])
    with open("./output/output.txt", "w") as f:
        output = llama_supernotes("docs")
        print("Llama output:", output)
        f.write(output)
    
    converttopdf("./output/output.txt")
    split_path_list = data["path"].split('/')
    print("Splitted path list", split_path_list)
    db_output_path = split_path_list[0] + '/' + split_path_list[1] + '/supernote/supernote.pdf'
    print("output path: ", db_output_path)
    upload_file(db_output_path, './output/supernote.pdf')
    # remove_temp_files()
    return "200"
@app.route("/test", methods=['GET'])
def test():
    return "hi"
@app.route("/clustering", methods=['POST'])
def run_clustering_keywords():
    data = request.json
    generate_all_txtfiles(data["path"])
    file_paths  = './docs'
    final_res = {}
    res = relevant_clustering(file_paths) # returns a dictionary
    final_res["keywords"] = res
    final_res["average"] = average_file_length("./docs")
    json_path = './output/cluster.json'
    with open(json_path, 'w') as json_file:
        json.dump(final_res, json_file)

    split_path_list = data["path"].split('/')
    db_output_path = split_path_list[0] + '/' + split_path_list[1] + '/clustering/cluster.json'
    upload_file(db_output_path, './output/cluster.json')
    # remove_temp_files()
    return jsonify(final_res)

# TODO: change the hardcoded user_file
@app.route("/similarity", methods=['POST'])
def calc_similarity_score():
    try: 
        data = request.json
        if not os.path.exists("./docs"):
            os.mkdir("./docs")
        remote_path = data["path"]
        print("Remote Path:", remote_path)
        remote_split = data["path"].split('/')
        print(remote_split)
        download_blob(remote_path, "./docs/student.pdf")
        print("Downloaded student.pdf")
        pdf_to_text("./docs/student.pdf", "./docs/student.txt")

        remote_path_super = remote_split[0] + '/' + remote_split[1] + '/supernote/supernote.pdf'
        download_blob(remote_path_super, "./docs/supernote.pdf")
        pdf_to_text("./docs/supernote.pdf", "./docs/supernote.txt")
        user_file, super_note = "./docs/student.txt", "./docs/supernote.txt" # output.txt is the supernote
        percent = calc_sim(user_file, super_note)
        # print(percent)
        percent *= 100
        return str(round(percent)) + "%", 200
    except:
        error_response = {'error': 'Field not found in JSON'}
        return jsonify(error_response), 400

def remove_temp_files():
    dirs = ['./docs', './output', './student_notes']
    for dir in dirs:
        if os.path.exists(dir):
            shutil.rmtree(dir)
        

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
