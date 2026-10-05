use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Broker {
    pub id: i64,
    pub code: String,
    pub name: String,
    pub website: Option<String>,
    pub is_active: bool,
    pub notes: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BrokerCapability {
    pub id: i64,
    pub broker_id: i64,
    pub market_type: String,
    pub operation_type: String,
    pub min_duration_seconds: Option<i64>,
    pub max_duration_seconds: Option<i64>,
    pub min_amount: Option<f64>,
    pub max_amount: Option<f64>,
    pub supports_demo: bool,
    pub supports_real: bool,
    pub notes: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BrokerAccount {
    pub id: i64,
    pub user_id: i64,
    pub broker_id: i64,
    pub account_type: String,
    pub account_number: Option<String>,
    pub active: bool,
    pub last_login_at: Option<String>,
    pub login_count: i64,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BrokerAccountSsid {
    pub id: i64,
    pub broker_account_id: i64,
    pub ssid: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BrokerAccountSigning {
    pub id: i64,
    pub broker_account_id: i64,
    pub username: String,
    pub password_encrypted: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BrokerAccountMetatrader {
    pub id: i64,
    pub broker_account_id: i64,
    pub login: String,
    pub password_encrypted: String,
    pub server: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OperationMetric {
    pub id: i64,
    pub signal_id: i64,
    pub broker_id: i64,
    pub account_mode: String,
    pub requested_amount: Option<f64>,
    pub executed_amount: Option<f64>,
    pub payout_percent: Option<f64>,
    pub spread: Option<f64>,
    pub slippage: Option<f64>,
    pub open_price: Option<f64>,
    pub close_price: Option<f64>,
    pub result: Option<String>,
    pub profit_loss: Option<f64>,
    pub latency_ms: Option<i64>,
    pub error_log: Option<String>,
    pub executed_at: String,
}

/// Dynamic request payload sent to the Python broker IPC script via stdin
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TradeRequest {
    pub broker: String,
    pub credentials: serde_json::Value,
    pub action: String,
    pub asset: String,
    pub amount: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duration: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sl: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tp: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timezone: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub entry_time: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub entry_price: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub entry_range: Option<(f64, f64)>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub verify_price: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tolerance: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub gale_steps: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub gale_multiplier: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub price_timeout: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metric_id: Option<i64>,
}

/// JSON payload returned by the Python broker IPC script via stdout
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TradeResult {
    pub success: bool,
    pub trade_id: Option<String>,
    pub result: Option<String>,
    pub balance_after: Option<f64>,
    #[serde(default)]
    pub current_price: Option<f64>,
    #[serde(default)]
    pub price_verified: Option<bool>,
    #[serde(default)]
    pub executed_amount: Option<f64>,
    #[serde(default)]
    pub profit_loss: Option<f64>,
    #[serde(default)]
    pub gale_step_won: Option<i64>,
    #[serde(default)]
    pub timeout: Option<bool>,
    pub error: Option<String>,
    #[serde(default)]
    pub traceback: Option<String>,
}

impl TradeResult {
    pub fn error(msg: impl Into<String>) -> Self {
        Self {
            success: false,
            error: Some(msg.into()),
            ..Default::default()
        }
    }

    pub fn error_with_traceback(msg: impl Into<String>, tb: impl Into<String>) -> Self {
        Self {
            success: false,
            error: Some(msg.into()),
            traceback: Some(tb.into()),
            ..Default::default()
        }
    }
}

/// Request payload to query the current market price of an asset from a broker
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceRequest {
    pub broker: String,
    pub credentials: serde_json::Value,
    pub action: String,
    pub asset: String,
}

/// Response payload from querying market price
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceResult {
    pub success: bool,
    pub price: Option<f64>,
    pub asset: Option<String>,
    pub broker: Option<String>,
    pub error: Option<String>,
}
