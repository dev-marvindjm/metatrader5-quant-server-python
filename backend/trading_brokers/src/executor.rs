use std::io::Write;
use std::process::{Command, Stdio};
use std::time::Instant;
use std::path::Path;

use crate::models::{TradeRequest, TradeResult};
use crate::python::detect_python_path;

pub struct BrokerExecutor {
    python_path: std::path::PathBuf,
    script_path: std::path::PathBuf,
}

impl BrokerExecutor {
    /// Creates a new BrokerExecutor, attempting to locate `execute_trade.py` inside the crate or working directory.
    pub fn new() -> Self {
        let python_path = detect_python_path();
        
        let possible_script_paths = [
            "trading_brokers/python/execute_trade.py",
            "python/execute_trade.py",
            "execute_trade.py",
            "../trading_brokers/python/execute_trade.py",
        ];

        let mut script_path = std::path::PathBuf::from("trading_brokers/python/execute_trade.py");
        for candidate in &possible_script_paths {
            if Path::new(candidate).exists() {
                script_path = std::path::PathBuf::from(candidate);
                break;
            }
        }

        Self {
            python_path,
            script_path,
        }
    }

    /// Sets a custom path for the Python interpreter script executor.
    pub fn with_script_path<P: AsRef<Path>>(mut self, path: P) -> Self {
        self.script_path = path.as_ref().to_path_buf();
        self
    }

    /// Executes a trade request by attempting to send it to the persistent broker daemon first, falling back to process execution.
    pub fn execute(&self, request: &TradeRequest) -> (TradeResult, u128) {
        let start = Instant::now();

        // 1. Try persistent in-memory session daemon at http://127.0.0.1:8090/trade
        if let Ok(client) = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(310))
            .build()
        {
            if let Ok(res) = client.post("http://127.0.0.1:8090/trade").json(request).send() {
                let duration = start.elapsed().as_millis();
                if res.status().is_success() {
                    if let Ok(trade_result) = res.json::<TradeResult>() {
                        return (trade_result, duration);
                    }
                }
            }
        }

        // 2. Fallback: Execute on-demand via execute_trade.py process
        let payload = match serde_json::to_string(request) {
            Ok(json) => json,
            Err(e) => {
                let duration = start.elapsed().as_millis();
                return (
                    TradeResult::error(format!("Failed to serialize TradeRequest: {}", e)),
                    duration,
                );
            }
        };

        let child = Command::new(&self.python_path)
            .arg(&self.script_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn();

        let mut child = match child {
            Ok(c) => c,
            Err(e) => {
                let duration = start.elapsed().as_millis();
                return (
                    TradeResult::error(format!("Failed to spawn Python process ({:?} {:?}): {}", self.python_path, self.script_path, e)),
                    duration,
                );
            }
        };

        if let Some(mut stdin) = child.stdin.take() {
            let _ = stdin.write_all(payload.as_bytes());
        }

        let output = match child.wait_with_output() {
            Ok(out) => out,
            Err(e) => {
                let duration = start.elapsed().as_millis();
                return (
                    TradeResult::error(format!("Failed to wait for Python process output: {}", e)),
                    duration,
                );
            }
        };

        let duration = start.elapsed().as_millis();
        let stdout_str = String::from_utf8_lossy(&output.stdout).trim().to_string();

        if stdout_str.is_empty() {
            let stderr_str = String::from_utf8_lossy(&output.stderr).to_string();
            return (
                TradeResult::error_with_traceback(
                    format!("Python script returned empty stdout. Stderr: {}", stderr_str),
                    stderr_str,
                ),
                duration,
            );
        }

        let json_line = stdout_str
            .lines()
            .rev()
            .find(|line| line.trim_start().starts_with('{'))
            .unwrap_or(&stdout_str);

        match serde_json::from_str::<TradeResult>(json_line) {
            Ok(result) => (result, duration),
            Err(e) => (
                TradeResult::error(format!("Failed to parse Python JSON stdout: {}. Raw output: {}", e, stdout_str)),
                duration,
            ),
        }
    }

    /// Executes a single Signal by converting it to a TradeRequest.
    pub fn execute_signal(
        &self,
        signal: &trading_signals_text_tokens::tokens::Signal,
        broker_code: &str,
        credentials: serde_json::Value,
        amount: f64,
    ) -> (TradeResult, u128) {
        self.execute_signal_with_timezone(signal, broker_code, credentials, amount, None)
    }

    /// Executes a single Signal by converting it to a TradeRequest with a fallback timezone.
    pub fn execute_signal_with_timezone(
        &self,
        signal: &trading_signals_text_tokens::tokens::Signal,
        broker_code: &str,
        credentials: serde_json::Value,
        amount: f64,
        fallback_timezone: Option<&str>,
    ) -> (TradeResult, u128) {
        self.execute_signal_full(signal, broker_code, credentials, amount, fallback_timezone, None, None)
    }

    /// Executes a Signal with full options including metric_id and price_timeout.
    pub fn execute_signal_full(
        &self,
        signal: &trading_signals_text_tokens::tokens::Signal,
        broker_code: &str,
        credentials: serde_json::Value,
        amount: f64,
        fallback_timezone: Option<&str>,
        metric_id: Option<i64>,
        price_timeout: Option<i64>,
    ) -> (TradeResult, u128) {
        match crate::signals::signal_to_trade_request_with_timezone(signal, broker_code, credentials, amount, fallback_timezone) {
            Ok(mut req) => {
                req.metric_id = metric_id;
                if price_timeout.is_some() {
                    req.price_timeout = price_timeout;
                }
                self.execute(&req)
            }
            Err(e) => (
                TradeResult::error(e),
                0,
            ),
        }
    }

    /// Executes a batch `Vec<Signal>` sequentially.
    pub fn execute_signals(
        &self,
        signals: &[trading_signals_text_tokens::tokens::Signal],
        broker_code: &str,
        credentials: serde_json::Value,
        amount: f64,
    ) -> Vec<(TradeResult, u128)> {
        let requests = crate::signals::signals_to_trade_requests(signals, broker_code, credentials, amount);
        requests.iter().map(|req| self.execute(req)).collect()
    }

    /// Queries the current market price for an asset from the specified broker.
    pub fn get_price(
        &self,
        broker_code: &str,
        credentials: serde_json::Value,
        asset: &str,
    ) -> (Result<f64, String>, u128) {
        let start = Instant::now();
        let payload = serde_json::json!({
            "broker": broker_code,
            "credentials": credentials,
            "action": "price",
            "asset": asset,
        });

        // 1. Try persistent in-memory session daemon at http://127.0.0.1:8090/price
        if let Ok(client) = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(15))
            .build()
        {
            if let Ok(res) = client.post("http://127.0.0.1:8090/price").json(&payload).send() {
                let duration = start.elapsed().as_millis();
                if res.status().is_success() {
                    if let Ok(price_res) = res.json::<crate::models::PriceResult>() {
                        if price_res.success {
                            if let Some(price) = price_res.price {
                                return (Ok(price), duration);
                            }
                        }
                    }
                }
            }
        }

        // 2. Fallback: Execute on-demand via execute_trade.py process
        let payload_str = match serde_json::to_string(&payload) {
            Ok(s) => s,
            Err(e) => return (Err(format!("Failed to serialize PriceRequest: {}", e)), start.elapsed().as_millis()),
        };

        let child = Command::new(&self.python_path)
            .arg(&self.script_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn();

        let mut child = match child {
            Ok(c) => c,
            Err(e) => return (Err(format!("Failed to spawn Python process: {}", e)), start.elapsed().as_millis()),
        };

        if let Some(mut stdin) = child.stdin.take() {
            let _ = stdin.write_all(payload_str.as_bytes());
        }

        let output = match child.wait_with_output() {
            Ok(out) => out,
            Err(e) => return (Err(format!("Failed to wait for price process: {}", e)), start.elapsed().as_millis()),
        };

        let duration = start.elapsed().as_millis();
        let stdout_str = String::from_utf8_lossy(&output.stdout).trim().to_string();

        if stdout_str.is_empty() {
            let stderr_str = String::from_utf8_lossy(&output.stderr).to_string();
            return (Err(format!("Empty output from price process. Stderr: {}", stderr_str)), duration);
        }

        let json_line = stdout_str
            .lines()
            .rev()
            .find(|line| line.trim_start().starts_with('{'))
            .unwrap_or(&stdout_str);

        match serde_json::from_str::<crate::models::PriceResult>(json_line) {
            Ok(result) => {
                if result.success {
                    if let Some(price) = result.price {
                        (Ok(price), duration)
                    } else {
                        (Err("Price result was success but price field was None".to_string()), duration)
                    }
                } else {
                    (Err(result.error.unwrap_or_else(|| "Unknown error fetching price".to_string())), duration)
                }
            }
            Err(e) => (Err(format!("Failed to parse PriceResult JSON: {}. Output: {}", e, stdout_str)), duration),
        }
    }

    /// Queries the current market price for a Symbol struct from the specified broker.
    pub fn get_symbol_price(
        &self,
        broker_code: &str,
        credentials: serde_json::Value,
        symbol: &trading_signals_text_tokens::tokens::Symbol,
    ) -> (Result<f64, String>, u128) {
        let asset = crate::signals::extract_symbol_name(symbol);
        self.get_price(broker_code, credentials, &asset)
    }
}
