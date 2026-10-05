use std::path::{Path, PathBuf};

/// Detects the Python binary path, prioritizing virtual environments (.venv/venv).
pub fn detect_python_path() -> PathBuf {
    let candidates = [
        ".venv/Scripts/python.exe",
        "venv/Scripts/python.exe",
        ".venv/bin/python",
        "venv/bin/python",
        "../.venv/Scripts/python.exe",
        "../venv/Scripts/python.exe",
        "../.venv/bin/python",
        "../venv/bin/python",
    ];

    for candidate in &candidates {
        let p = Path::new(candidate);
        if p.exists() {
            return p.to_path_buf();
        }
    }

    PathBuf::from("python")
}

/// Detects the Pip or uv binary path, prioritizing uv then virtual environments (.venv/venv).
pub fn detect_pip_path() -> (PathBuf, Vec<String>) {
    // Check if uv is available in PATH
    if let Ok(output) = std::process::Command::new("uv").arg("--version").output() {
        if output.status.success() {
            return (PathBuf::from("uv"), vec!["pip".to_string(), "install".to_string()]);
        }
    }

    let candidates = [
        ".venv/Scripts/pip.exe",
        "venv/Scripts/pip.exe",
        ".venv/bin/pip",
        "venv/bin/pip",
        "../.venv/Scripts/pip.exe",
        "../venv/Scripts/pip.exe",
        "../.venv/bin/pip",
        "../venv/bin/pip",
    ];

    for candidate in &candidates {
        let p = Path::new(candidate);
        if p.exists() {
            return (p.to_path_buf(), vec!["install".to_string()]);
        }
    }

    (PathBuf::from("pip"), vec!["install".to_string()])
}

/// Installs a Python package using uv (if available) or pip.
pub fn install_python_package(package_name: &str) -> Result<bool, String> {
    let (cmd_path, mut base_args) = detect_pip_path();
    base_args.push(package_name.to_string());

    let output = std::process::Command::new(cmd_path)
        .args(&base_args)
        .output()
        .map_err(|e| format!("Failed to execute package installer: {:?}", e))?;

    if output.status.success() {
        Ok(true)
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("Package installation failed: {}", stderr))
    }
}
