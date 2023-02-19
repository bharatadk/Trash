import mimetypes
from math import ceil
from typing import List
from shiny import App, render, ui,reactive
from shiny import *
import os
import uuid
import shutil
from datetime import datetime, date
from htmltools import HTML, div
import sqlite3
import pickle
import fitz


all_results = []


def save_task_to_database(
    filenames, date="0", time="0", filetype="pdf", email="example@gmail.com"
):
    # Connect to SQLite database
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    serialized_filenames = pickle.dumps(filenames)

    # Create tasks table if it doesn't exist
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            date TEXT,
            time TEXT,
            filenames BLOB,
            filetype TEXT,
            result TEXT,
            status TEXT
        )
    """
    )

    # Save task to database
    cursor.execute(
        """
        INSERT INTO tasks (email, date,time,filenames,filetype, status)
        VALUES (?,?,?,?,?, 'pending')
    """,
        (email, date, time, serialized_filenames, filetype),
    )

    conn.commit()
    # cursor.close()
    conn.close()

    task_id = cursor.lastrowid
    return task_id


##################################################################
##################################################################
#                      UI

os.environ["GPU"] = ""


UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.environ["UPLOAD_FOLDER"] = UPLOAD_FOLDER

app_ui = ui.page_fluid(
    ui.input_text("time1", "Enter Time (24 hr format) ", value="8:30"),
    ui.input_date("date1", "Date:", format="mm/dd/yy"),
    ui.input_file(
        "file1", "Choose a file to upload:", accept="application/pdf", multiple=False
    ),

    ui.output_text_verbatim("file_content"),
    ui.input_action_button("btn", "Submit",class_="btn-success"),
    ui.h3("Result Table:"),
    ui.output_text_verbatim("current_time1", placeholder=True),
    ui.h6(
        "[ task-id ] - [ date ] - - - -  [ time ] - [ STATUS ]  - - - -  - - [ RESULT ]"
    ),
    ui.output_text_verbatim("txt1", placeholder=True),
)

##################################################################
##################################################################
#                      SERVER


def server(input, output, session):

    @reactive.Effect
    @reactive.event(input.btn)
    def _():
        print(f"You clicked the button!")
        # You can do other things here, like write data to disk.

    @output
    @render.text
    @reactive.event(input.btn)
    def file_content():

        # INPUT_DATE_TIME

        if input.date1() is None:
            return "Please Enter date"
        date1 = input.date1()
        time1 = input.time1()

        # INPUT_PDF_FILE

        filenames = []
        # Create the directory if it doesn't exist
        if not os.path.exists(os.environ["UPLOAD_FOLDER"]):
            os.mkdir(os.environ["UPLOAD_FOLDER"])
        if input.file1() is None:
            return "Please upload a pdf file"
        f: list[FileInfo] = input.file1()
        filename = str(uuid.uuid4()) + ".pdf"
        new_path = f[0]["datapath"].split(".")[0] + filename
        os.rename(f[0]["datapath"], new_path)
        f[0]["datapath"] = new_path
        new_loc = os.environ["UPLOAD_FOLDER"]
        shutil.copy(f[0]["datapath"], new_loc)
        filenames.append("0" + filename)
        save_task_to_database(filenames, date1, time1)

        return ""

    @output
    @render.text
    def current_time1():
        return "Current Server Time : " + str(datetime.now())



    @output
    @render.text
    def txt1():
        try:
            conn = sqlite3.connect("tasks.db")
            cursor = conn.cursor()

            # Get all  tasks
            cursor.execute(
                """
                SELECT task_id,date,time,status,result
                FROM tasks
            """
            )
            tasks = cursor.fetchall()
            all_results = []
            for task_id, date, time, status, result in tasks:
                if result is None:
                    result = ""
                result = result.replace(" ", "").replace("\n", "")
                temp = [str(task_id), date, time, status, result[:50] + "..."]
                all_results.append(temp)
            cursor.close()
            conn.close()
            d = ""
            all = ""
            for row in all_results:
                d = "\t".join(row)
                all = all + d + "\n"
            return all
        except Exception as e:
            # print("Error in Reading Database", e)
            return " There are no files in database"


app = App(app_ui, server)
from apscheduler.schedulers.background import BackgroundScheduler

# from schedule.schedule import verify_and_run_schedule


def run_scheduled_tasks():
    try:
        # Connect to SQLite database
        conn = sqlite3.connect("tasks.db")
        cursor = conn.cursor()

        # Get all pending tasks
        cursor.execute(
            """
            SELECT task_id, email, date,time,filenames,filetype
            FROM tasks
            WHERE  status = 'pending'
        """
        )
        tasks = cursor.fetchall()

        # Run tasks that are due
        for task_id, email, date, time, filenames, filetype in tasks:
            # Convert the date and time from the form into a datetime object
            form_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            # Get the current date and time
            current_datetime = datetime.now()

            if current_datetime >= form_datetime:
                print("current time is greater", current_datetime, form_datetime)
                if filetype == "img":
                    pass
                else:
                    result = pdf_to_text(pickle.loads(filenames))
                    # print(result)
                cursor.execute(
                    """
                    UPDATE tasks
                    SET status = 'finished', result = ?
                    WHERE task_id = ?
                """,
                    (result, task_id),
                )
        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        print("🐛 in run_scheduled_tasks", e)
    return


# check if database + table exists + len(rows)>0
def verify_and_run_schedule():
    try:
        database_name = "tasks.db"
        table_name = "tasks"
        if not os.path.exists(database_name):
            print("Database doesnot exist")
            return

        conn = sqlite3.connect(database_name)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name from sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        table_exists = cursor.fetchone() is not None

        if table_exists:
            cursor.execute("SELECT count(*) FROM {}".format(table_name))
            rows = cursor.fetchone()
            table_not_empty = rows[0] > 0
        else:
            table_not_empty = False
            print("⏰ Table doesn't exist or no any tasks to run ")
            cursor.close()
            conn.close()
            return

        cursor.close()
        conn.close()
        if table_exists and table_not_empty:
            run_scheduled_tasks()
            return
        return
    except Exception as e:
        print("🐛 in verify_and_run_schedule", e)


def pdf_to_text(filenames):
    try:
        pdf_document = fitz.open(
            os.path.join(os.environ["UPLOAD_FOLDER"], filenames[0])
        )
        text = ""
        count = 1
        for page in pdf_document:
            text += page.get_text("text")
            count = count + 1
            if count >= 6:
                return text
        return text
    except Exception as e:
        print(e)


scheduler = BackgroundScheduler()
scheduler.add_job(verify_and_run_schedule, trigger="interval", seconds=60)
scheduler.start()
