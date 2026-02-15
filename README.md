# localwriter: A LibreOffice Writer extension for local generative AI

Consider donating to support development: https://ko-fi.com/johnbalis

## About

This is a LibreOffice Writer extension that enables inline generative editing with local inference. It's compatible with language models supported by `text-generation-webui` and `ollama`.

## Table of Contents

*   [About](#about)
*   [Table of Contents](#table-of-contents)
*   [Features](#features)
    *   [Extend Selection](#extend-selection)
    *   [Edit Selection](#edit-selection)
*   [Setup](#setup)
    *   [LibreOffice Extension Installation](#libreoffice-extension-installation)
    *   [Backend Setup](#backend-setup)
        *   [text-generation-webui](#text-generation-webui)
        *   [Ollama](#ollama)
*   [Settings](#settings)
*   [Contributing](#contributing)
    *   [Local Development Setup](#local-development-setup)
    *   [Building the Extension Package](#building-the-extension-package)
*   [License](#license)

## Features

This extension provides two powerful commands for LibreOffice Writer:

### Extend Selection

**Hotkey:** `CTRL + q`

*   This uses a language model to predict what comes after the selected text. There are a lot of ways to use this.
*   Some example use cases for this include: writing a story or an email given a particular prompt, adding additional possible items to a grocery list, or summarizing the selected text.

### Edit Selection

**Hotkey:** `CTRL + e`

*   A dialog box appears to prompt the user for instructions about how to edit the selected text, then the selected text is replaced by the edited text.
*   Some examples for use cases for this include changing the tone of an email, translating text to a different language, and semantically editing a scene in a story.

## Setup

### LibreOffice Extension Installation

1.  Download the latest version of Localwriter via the [releases page](https://github.com/balisujohn/localwriter/releases).
2.  Open LibreOffice.
3.  Navigate to `Tools > Extensions`.
4.  Click `Add` and select the downloaded `.oxt` file.
5.  Follow the on-screen instructions to install the extension.

### Backend Setup

To use Localwriter, you need a backend model runner.  Options include `text-generation-webui` and `Ollama`. Choose the backend that best suits your needs. Ollama is generally easier to set up. In either of these options, you will have to download and set a model. 

#### text-generation-webui

*   Installation instructions can be found [here](https://github.com/oobabooga/text-generation-webui).
*   Docker image available [here](https://github.com/Atinoda/text-generation-webui-docker).

After installation and model setup:

1.  Enable the local OpenAI API (this ensures the API responds in a format similar to OpenAI).
2.  Verify that the intended model is working (e.g., openchat3.5, suitable for 8GB VRAM setups).
3.  Set the endpoint in Localwriter settings to `http://localhost:5000` (or the configured port). The default endpoint changed to Ollama's port (11434) in version 0.0.9, so text-generation-webui users must set this explicitly.

#### Ollama

*   Installation instructions are available [here](https://ollama.com/).
*   Download and use a model (gemma3 isn't bad)
*   Ensure the API is enabled.
*   Set the endpoint in Localwriter to `localhost:11434` (or the configured port).
*   Manually set the model name. ([This is required for Ollama to work](https://ask.libreoffice.org/t/localwriter-0-0-5-installation-and-usage/122241/5?u=jbalis))

## Settings

Settings can be configured via the settings dialog in LibreOffice (localwriter menu > Settings).

Configuration file location:
- macOS: `~/Library/Application Support/LibreOffice/4/user/localwriter.json`
- Linux: `~/.config/libreoffice/4/user/localwriter.json`
- Windows: `%APPDATA%\LibreOffice\4\user\localwriter.json`

### Available Settings

*   **Endpoint URL**: The URL of your LLM server (default: `http://localhost:11434` for Ollama)
*   **Model**: The model name (e.g., `llama2`, `gpt-3.5-turbo`)
*   **API Key**: Authentication key for OpenAI-compatible endpoints (optional for local servers)
*   **API Type**: `completions` (default) or `chat` — use `chat` for OpenAI or servers with a `/chat/completions` endpoint
*   **Is OpenWebUI endpoint?**: Set to `true` if using OpenWebUI (changes API path from `/v1/` to `/api/`)
*   **OpenAI Compatible Endpoint?**: Set to `true` for servers that strictly follow OpenAI format
*   **Disable SSL Verification**: Set to `true` to skip certificate checks — only use for local servers with self-signed certs
*   **Extend Selection Max Tokens**: Maximum number of tokens for text extension
*   **Extend Selection System Prompt**: Instructions prepended to guide the model's style for extension
*   **Edit Selection Max New Tokens**: Additional tokens allowed above original selection length
*   **Edit Selection System Prompt**: Instructions for guiding text editing behavior

## Contributing

Help with development is always welcome. localwriter has a number of outstanding feature requests by users. Feel free to work on any of them, and you can help improve freedom-respecting local AI.

### Local Development Setup

For developers who want to modify or contribute to Localwriter, you can run and test the extension directly from your source code without packaging it into an `.oxt` file. This allows for quick iteration and seeing changes reflected in the LibreOffice UI.

1. **Clone the Repository (if not already done):**
   - Clone the Localwriter repository to your local machine if you haven't already:
     ```
     git clone https://github.com/balisujohn/localwriter.git
     cd localwriter
     ```

2. **Register the Extension Temporarily:**
   - Use the `unopkg` tool to register the extension directly from your repository folder. This avoids the need to package the extension as an `.oxt` file during development.
   - Run the following command, replacing `/path/to/localwriter/` with the path to your cloned repository:
     ```
     unopkg add /path/to/localwriter/
     ```
   - On Linux, `unopkg` is often located at `/usr/lib/libreoffice/program/unopkg`. Adjust the command if needed:
     ```
     /usr/lib/libreoffice/program/unopkg add /path/to/localwriter/
     ```

3. **Restart LibreOffice:**
   - Close and reopen LibreOffice Writer or Calc. You should see the "localwriter" menu with options like "Extend Selection", "Edit Selection", and "Settings" in the menu bar.

4. **Make and Test Changes:**
   - Edit the source files (e.g., `main.py`) directly in your repository folder using your preferred editor.
   - After making changes, restart LibreOffice to reload the updated code. Test the functionality and UI elements (dialogs, menu actions) directly in LibreOffice.
   - Note: Restarting is often necessary for Python script changes to take effect, as LibreOffice caches modules.

5. **Commit Changes to Git:**
   - Since you're working directly in your Git repository, commit your changes as needed:
     ```
     git add main.py
     git commit -m "Updated extension logic for ExtendSelection"
     ```

6. **Unregister the Extension (Optional):**
   - If you need to remove the temporary registration, use:
     ```
     unopkg remove org.extension.sample
     ```
   - Replace `org.extension.sample` with the identifier from `description.xml` if different.

### Building the Extension Package

To create a distributable `.oxt` package:

In a terminal, change directory into the localwriter repository top-level directory, then run the following command:

````
zip -r localwriter.oxt \
  Accelerators.xcu \
  Addons.xcu \
  assets \
  description.xml \
  main.py \
  pythonpath \
  META-INF \
  registration \
  README.md
````

This will create the file `localwriter.oxt` which you can open with libreoffice to install the localwriter extension. You can also change the file extension to .zip and manually unzip the extension file, if you want to inspect a localwriter `.oxt` file yourself. It is all human-readable, since python is an interpreted language.



## License 

(See `License.txt` for the full license text)

Except where otherwise noted in source code, this software is provided with a MPL 2.0 license.

The code not released with an MPL2.0 license is released under the following terms.
License: Creative Commons Attribution-ShareAlike 3.0 Unported License,
License: The Document Foundation  https://creativecommons.org/licenses/by-sa/3.0/

A large amount of code is derived from the following MPL2.0 licensed code from the Document Foundation
https://gerrit.libreoffice.org/c/core/+/159938 


MPL2.0

Copyright (c) 2024 John Balis
