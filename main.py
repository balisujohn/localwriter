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
from com.sun.star.awt import MessageBoxButtons as MSG_BUTTONS

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
    
    #retrieved from https://wiki.documentfoundation.org/Macros/General/IO_to_Screen
    #License: Creative Commons Attribution-ShareAlike 3.0 Unported License,
    #License: The Document Foundation  https://creativecommons.org/licenses/by-sa/3.0/
    #begin sharealike section 
    def input_box(self,message, title="", default="", x=None, y=None):
        """ Shows dialog with input box.
            @param message message to show on the dialog
            @param title window title
            @param default default value
            @param x optional dialog position in twips
            @param y optional dialog position in twips
            @return string if OK button pushed, otherwise zero length string
        """
        WIDTH = 600
        HORI_MARGIN = VERT_MARGIN = 8
        BUTTON_WIDTH = 100
        BUTTON_HEIGHT = 26
        HORI_SEP = VERT_SEP = 8
        LABEL_HEIGHT = BUTTON_HEIGHT * 2 + 5
        EDIT_HEIGHT = 24
        HEIGHT = VERT_MARGIN * 2 + LABEL_HEIGHT + VERT_SEP + EDIT_HEIGHT
        import uno
        from com.sun.star.awt.PosSize import POS, SIZE, POSSIZE
        from com.sun.star.awt.PushButtonType import OK, CANCEL
        from com.sun.star.util.MeasureUnit import TWIP
        ctx = uno.getComponentContext()
        def create(name):
            return ctx.getServiceManager().createInstanceWithContext(name, ctx)
        dialog = create("com.sun.star.awt.UnoControlDialog")
        dialog_model = create("com.sun.star.awt.UnoControlDialogModel")
        dialog.setModel(dialog_model)
        dialog.setVisible(False)
        dialog.setTitle(title)
        dialog.setPosSize(0, 0, WIDTH, HEIGHT, SIZE)
        def add(name, type, x_, y_, width_, height_, props):
            model = dialog_model.createInstance("com.sun.star.awt.UnoControl" + type + "Model")
            dialog_model.insertByName(name, model)
            control = dialog.getControl(name)
            control.setPosSize(x_, y_, width_, height_, POSSIZE)
            for key, value in props.items():
                setattr(model, key, value)
        label_width = WIDTH - BUTTON_WIDTH - HORI_SEP - HORI_MARGIN * 2
        add("label", "FixedText", HORI_MARGIN, VERT_MARGIN, label_width, LABEL_HEIGHT, 
            {"Label": str(message), "NoLabel": True})
        add("btn_ok", "Button", HORI_MARGIN + label_width + HORI_SEP, VERT_MARGIN, 
                BUTTON_WIDTH, BUTTON_HEIGHT, {"PushButtonType": OK, "DefaultButton": True})
        add("edit", "Edit", HORI_MARGIN, LABEL_HEIGHT + VERT_MARGIN + VERT_SEP, 
                WIDTH - HORI_MARGIN * 2, EDIT_HEIGHT, {"Text": str(default)})
        frame = create("com.sun.star.frame.Desktop").getCurrentFrame()
        window = frame.getContainerWindow() if frame else None
        dialog.createPeer(create("com.sun.star.awt.Toolkit"), window)
        if not x is None and not y is None:
            ps = dialog.convertSizeToPixel(uno.createUnoStruct("com.sun.star.awt.Size", x, y), TWIP)
            _x, _y = ps.Width, ps.Height
        elif window:
            ps = window.getPosSize()
            _x = ps.Width / 2 - WIDTH / 2
            _y = ps.Height / 2 - HEIGHT / 2
        dialog.setPosSize(_x, _y, 0, 0, POS)
        edit = dialog.getControl("edit")
        edit.setSelection(uno.createUnoStruct("com.sun.star.awt.Selection", 0, len(str(default))))
        edit.setFocus()
        ret = edit.getModel().Text if dialog.execute() else ""
        dialog.dispose()
        return ret
    #end sharealike section 

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
            
        
            try:
                user_input= self.input_box("Please enter edit instructions!", "Input", "")
                text_range = selection.getByIndex(0)
                #text_range.setString(text_range.getString() + ": " + user_input)
                
                url = 'http://127.0.0.1:5000/v1/completions'
                headers = {
                    'Content-Type': 'application/json'
                }
                data = {
		        	'prompt': "ORIGINAL VERSION:\n" + cursor.getString() + "\n Below is an edited version according to the following instructions. There are no comments in the edited version. The edited version is followed by the end of the document: \n"+user_input+"\nEDITED VERSION:\n",   
                    'max_tokens': len(cursor.getString()),
                    'temperature': 1,
                    'top_p': 0.9,
                    'seed': 10
                }

                response = requests.post(url, headers=headers, data=json.dumps(data))

                if response.status_code == 200:
                    # Append completion to selection
                    selected_text = cursor.getString()
                    new_text = response.json()["choices"][0]["text"]

                    # Set the new text
                    cursor.setString(new_text)

                    # Set the cursor to select the newly added text and original text
                    #start = cursor.getStart()
                    #end = cursor.getEnd() + len(response.json()["choices"][0]["text"])
                    #cursor.setRange(start, end)


                    #text_range.setString(text_range.getString() + + str(start_index) + str(end_index))
                else:
                    pass
            except Exception as e:
                text_range = selection.getByIndex(0)
                # Append the user input to the selected text
                text_range.setString(text_range.getString() + ": " + str(e))
        

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
