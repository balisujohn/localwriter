# -*- tab-width: 4; indent-tabs-mode: nil; py-indent-offset: 4 -*-
#
# This file is part of the LibreOffice project.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
import sys
import unohelper
import officehelper
import requests
import json
from com.sun.star.task import XJobExecutor

# The MainJob is a UNO component derived from unohelper.Base class
# and also the XJobExecutor, the implemented interface
class MainJob(unohelper.Base, XJobExecutor):
    def __init__(self, ctx):
        self.ctx = ctx
        # handling different situations (inside LibreOffice or other process)
        try:
            self.sm = ctx.getServiceManager()
            self.desktop = XSCRIPTCONTEXT.getDesktop()
        except NameError:
            self.sm = ctx.ServiceManager
            self.desktop = self.ctx.getServiceManager().createInstanceWithContext(
                "com.sun.star.frame.Desktop", self.ctx)
    def trigger(self, args):
        desktop = self.ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", self.ctx)
        model = desktop.getCurrentComponent()
        if not hasattr(model, "Text"):
            model = self.desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, ())
        text = model.Text
        cursor = model.CurrentController.getViewCursor()                
       
        if args == "ExtendSelection":
            # Access the current selection
            #selection = model.CurrentController.getSelection()
            if len(cursor.getString()) > 0:
                # Get the first range of the selection
                #text_range = selection.getByIndex(0)

                url = 'http://127.0.0.1:5000/v1/completions'
                headers = {
                    'Content-Type': 'application/json'
                }
                data = {
                    'prompt': cursor.getString(),
                    'max_tokens': 70,
                    'temperature': 1,
                    'top_p': 0.9,
                    'seed': 10
                }

                response = requests.post(url, headers=headers, data=json.dumps(data))

                if response.status_code == 200:
                    # Append completion to selection
                    selected_text = cursor.getString()
                    new_text = selected_text + response.json()["choices"][0]["text"]

                    # Set the new text
                    cursor.setString(new_text)

                    # Set the cursor to select the newly added text and original text
                    start = cursor.getStart()
                    end = cursor.getEnd() + len(response.json()["choices"][0]["text"])
                    cursor.setRange(start, end)


                    #text_range.setString(text_range.getString() + + str(start_index) + str(end_index))
                else:
                    pass

        elif args == "EditSelection":
            # Access the current selection
            selection = model.CurrentController.getSelection()
            if selection.getCount() > 0:
                # Get the first range of the selection
                text_range = selection.getByIndex(0)
                # Append 10 zeros at the end of the selected text
                text_range.setString(text_range.getString() + ": unimplemented for now")
                    


# Starting from Python IDE
def main():
    try:
        ctx = XSCRIPTCONTEXT
    except NameError:
        ctx = officehelper.bootstrap()
        if ctx is None:
            print("ERROR: Could not bootstrap default Office.")
            sys.exit(1)
    job = MainJob(ctx)
    job.trigger("hello")
# Starting from command line
if __name__ == "__main__":
    main()
# pythonloader loads a static g_ImplementationHelper variable
g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    MainJob,  # UNO object class
    "org.extension.sample.do",  # implementation name (customize for yourself)
    ("com.sun.star.task.Job",), )  # implemented services (only 1)
# vim: set shiftwidth=4 softtabstop=4 expandtab:
