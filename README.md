# Paper Digest

A simple app to aggregate research papers from your favorite journals.

## Quick Start

### 1. Installation

Clone the repository and enter the directory:
```bash
git clone [https://github.com/BryanMcd/paper-digest-app](https://github.com/BryanMcd/paper-digest-app)
cd paper-digest-app
```

Run the installer script to set up the `paperdigest` command on your system.
```bash
bash install.sh
```

### 2. Run the app

>**Note:** You must provide your email address to authenticate with the OpenAlex API (this puts you in the "Polite Pool" for faster access).

```bash
# Replace with your actual email
PD_MAILTO="your@email.com" paperdigest