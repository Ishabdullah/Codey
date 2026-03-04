#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  Codey Installer — Full setup on a fresh Termux install
#  Usage: bash install.sh
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${CYAN}ℹ  $1${NC}"; }
success() { echo -e "${GREEN}✓  $1${NC}"; }
warning() { echo -e "${YELLOW}⚠  $1${NC}"; }
error()   { echo -e "${RED}✗  $1${NC}"; exit 1; }
header()  { echo -e "\n${BOLD}${CYAN}── $1 ──${NC}\n"; }

# ── Paths ────────────────────────────────────────────────────
HOME_DIR="$HOME"
CODEY_DIR="$HOME_DIR/codey"
LLAMA_DIR="$HOME_DIR/llama.cpp"
MODEL_DIR="$HOME_DIR/models/qwen2.5-coder-7b"
MODEL_FILE="$MODEL_DIR/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf"
MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
CODEY_REPO="https://github.com/Ishabdullah/Codey.git"

echo -e "${BOLD}${GREEN}"
echo "  ██████╗ ██████╗ ██████╗ ███████╗██╗   ██╗"
echo " ██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗ ██╔╝"
echo " ██║     ██║   ██║██║  ██║█████╗   ╚████╔╝ "
echo " ██║     ██║   ██║██║  ██║██╔══╝    ╚██╔╝  "
echo " ╚██████╗╚██████╔╝██████╔╝███████╗   ██║   "
echo "  ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝   ╚═╝   "
echo -e "${NC}"
echo -e "${BOLD}  Codey Installer — Local AI Coding Assistant for Termux${NC}"
echo ""
echo "  This will install:"
echo "  • System packages (python, git, clang, cmake, etc.)"
echo "  • llama.cpp (compiled from source)"
echo "  • Qwen2.5-Coder-7B-Instruct Q4_K_M (~4.5 GB)"
echo "  • Codey and Python dependencies"
echo ""
echo "  Requirements:"
echo "  • ~8 GB free storage"
echo "  • ~5 GB free RAM at runtime"
echo "  • Stable internet connection for model download"
echo ""
read -p "  Continue? [Y/n]: " confirm
if [[ "$confirm" =~ ^[Nn]$ ]]; then
    echo "Aborted."
    exit 0
fi

# ── Step 1: System packages ───────────────────────────────────
header "Step 1/6: System packages"
info "Updating package lists..."
pkg update -y -o Dpkg::Options::="--force-confnew" 2>/dev/null || true
pkg upgrade -y -o Dpkg::Options::="--force-confnew" 2>/dev/null || true

info "Installing required packages..."
pkg install -y \
    python \
    git \
    clang \
    cmake \
    make \
    ninja \
    wget \
    curl \
    openssh \
    libandroid-execinfo \
    2>/dev/null || error "Failed to install system packages"

success "System packages installed."

# ── Step 2: Python dependencies ───────────────────────────────
header "Step 2/6: Python dependencies"
pip install --upgrade pip --break-system-packages -q
pip install rich pytest --break-system-packages -q
success "Python dependencies installed (rich, pytest)."

# ── Step 3: llama.cpp ─────────────────────────────────────────
header "Step 3/6: Building llama.cpp"

if [ -f "$LLAMA_DIR/build/bin/llama-server" ]; then
    warning "llama.cpp already built at $LLAMA_DIR — skipping."
else
    info "Cloning llama.cpp..."
    rm -rf "$LLAMA_DIR"
    git clone --depth=1 https://github.com/ggerganov/llama.cpp.git "$LLAMA_DIR"

    info "Building llama-server (this takes 5-15 minutes)..."
    cd "$LLAMA_DIR"
    cmake -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DLLAMA_CURL=OFF \
        -DGGML_NATIVE=OFF \
        2>/dev/null
    cmake --build build --config Release -j$(nproc) --target llama-server 2>/dev/null

    if [ ! -f "$LLAMA_DIR/build/bin/llama-server" ]; then
        error "llama-server build failed. Check cmake output above."
    fi
    success "llama.cpp built successfully."
fi

# ── Step 4: Download model ────────────────────────────────────
header "Step 4/6: Downloading model"

if [ -f "$MODEL_FILE" ]; then
    success "Model already exists at $MODEL_FILE — skipping download."
else
    mkdir -p "$MODEL_DIR"

    # Check available storage
    AVAIL=$(df -BG "$HOME_DIR" | awk 'NR==2 {print $4}' | tr -d 'G')
    if [ "$AVAIL" -lt 5 ] 2>/dev/null; then
        warning "Low storage: ${AVAIL}GB available. Model requires ~4.5GB."
        read -p "  Continue anyway? [y/N]: " storage_ok
        if [[ ! "$storage_ok" =~ ^[Yy]$ ]]; then
            error "Aborted. Free up storage and re-run."
        fi
    fi

    info "Downloading Qwen2.5-Coder-7B-Instruct-Q4_K_M (~4.5 GB)..."
    info "This may take 30-90 minutes depending on your connection."
    echo ""

    wget -q --show-progress \
        --continue \
        -O "$MODEL_FILE" \
        "$MODEL_URL" \
    || curl -L \
        --progress-bar \
        --continue-at - \
        -o "$MODEL_FILE" \
        "$MODEL_URL" \
    || error "Model download failed. Check your internet connection and retry."

    # Verify size (should be > 4GB)
    SIZE=$(stat -c%s "$MODEL_FILE" 2>/dev/null || echo 0)
    if [ "$SIZE" -lt 4000000000 ]; then
        warning "Downloaded file seems too small (${SIZE} bytes). May be incomplete."
        warning "Re-run install.sh to resume the download."
    else
        success "Model downloaded ($(du -sh "$MODEL_FILE" | cut -f1))."
    fi
fi

# ── Step 5: Clone Codey ───────────────────────────────────────
header "Step 5/6: Installing Codey"

if [ -d "$CODEY_DIR/.git" ]; then
    info "Codey already installed — pulling latest..."
    cd "$CODEY_DIR"
    git pull --ff-only 2>/dev/null || warning "Could not pull latest (local changes?)"
else
    info "Cloning Codey..."
    git clone "$CODEY_REPO" "$CODEY_DIR"
fi

# Make wrapper executable
chmod +x "$CODEY_DIR/codey"
success "Codey installed at $CODEY_DIR."

# ── Step 6: PATH setup ────────────────────────────────────────
header "Step 6/6: Configuring shell"

BASHRC="$HOME_DIR/.bashrc"
PROFILE="$HOME_DIR/.profile"

add_to_file() {
    local file="$1"
    local line="$2"
    grep -qxF "$line" "$file" 2>/dev/null || echo "$line" >> "$file"
}

PATH_LINE='export PATH="$HOME/codey:$PATH"'
add_to_file "$BASHRC"  "$PATH_LINE"
add_to_file "$PROFILE" "$PATH_LINE"

# Also export for current session
export PATH="$CODEY_DIR:$PATH"

success "PATH configured."

# ── Verify installation ───────────────────────────────────────
header "Verifying installation"

ERRORS=0

check() {
    local label="$1"
    local path="$2"
    if [ -e "$path" ]; then
        success "$label"
    else
        error_msg "$label — not found at $path"
        ERRORS=$((ERRORS + 1))
    fi
}

error_msg() { echo -e "${RED}✗  $1${NC}"; }

check "llama-server binary"  "$LLAMA_DIR/build/bin/llama-server"
check "Model file"           "$MODEL_FILE"
check "Codey main.py"        "$CODEY_DIR/main.py"
check "Codey wrapper"        "$CODEY_DIR/codey"

python3 -c "import rich" 2>/dev/null && success "Python: rich" || { error_msg "Python: rich missing"; ERRORS=$((ERRORS+1)); }
python3 -c "import pytest" 2>/dev/null && success "Python: pytest" || { error_msg "Python: pytest missing"; ERRORS=$((ERRORS+1)); }

if [ $ERRORS -gt 0 ]; then
    echo ""
    warning "$ERRORS issue(s) found. Re-run install.sh to fix."
else
    echo ""
    echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
    echo -e "${BOLD}${GREEN}  Installation complete!${NC}"
    echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
    echo ""
    echo -e "  Run ${BOLD}source ~/.bashrc${NC} then type ${BOLD}codey${NC} to start."
    echo ""
    echo -e "  Quick start:"
    echo -e "    ${CYAN}codey${NC}                          # interactive mode"
    echo -e "    ${CYAN}codey \"create hello.py\"${NC}        # one-shot task"
    echo -e "    ${CYAN}codey --init${NC}                   # generate project memory"
    echo -e "    ${CYAN}codey --tdd app.py --tests t.py${NC} # TDD mode"
    echo -e "    ${CYAN}codey --help${NC}                   # all options"
    echo ""
    echo -e "  First run loads the model (~15s). Subsequent queries are faster."
    echo ""
fi
