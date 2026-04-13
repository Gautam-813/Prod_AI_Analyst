"""
Python Code Execution Sandbox for AI Analysis
Safely executes AI-generated Python code with access to data analysis libraries
"""

import io
import sys
import contextlib
import traceback
import pandas as pd
import numpy as np
from typing import Dict, Optional, Any
import plotly.graph_objects as go
import plotly.express as px
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import json
import re
import math
import warnings

# Suppress warnings in sandbox
warnings.filterwarnings('ignore')

# Optional imports (graceful fallback)
try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    import sklearn
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import statsmodels.api as sm
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False

try:
    import scipy
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

try:
    import polars as pl
    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False

try:
    import altair as alt
    ALTAIR_AVAILABLE = True
except ImportError:
    ALTAIR_AVAILABLE = False

try:
    import quantstats as qs
    QUANTSTATS_AVAILABLE = True
except ImportError:
    QUANTSTATS_AVAILABLE = False

try:
    import mplfinance as mpf
    MPLFINANCE_AVAILABLE = True
except ImportError:
    MPLFINANCE_AVAILABLE = False


class CodeSandbox:
    """Safe Python code execution environment for AI-generated analysis"""

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.stdout_buffer = io.StringIO()
        self.figures = []  # Store generated plotly figures
        self.plots = []    # Store generated matplotlib images

    def execute(self, code: str) -> Dict[str, Any]:
        """
        Execute Python code in sandboxed environment
        Returns: {
            "success": bool,
            "stdout": str,
            "error": str or None,
            "plots": list of base64 encoded images,
            "figures": list of plotly JSON configs
        }
        """
        result = {
            "success": False,
            "stdout": "",
            "error": None,
            "plots": [],
            "figures": []
        }

        # Build execution environment
        env = self._build_environment()

        # Capture stdout and stderr
        try:
            with contextlib.redirect_stdout(self.stdout_buffer), \
                 contextlib.redirect_stderr(self.stdout_buffer):
                exec(code, env)

            result["success"] = True
            result["stdout"] = self.stdout_buffer.getvalue()
            result["figures"] = self.figures
            result["plots"] = self.plots

        except Exception as e:
            result["error"] = f"{type(e).__name__}: {str(e)}"
            result["stdout"] = self.stdout_buffer.getvalue()
            # Include partial output if any

        return result

    def _build_environment(self) -> Dict[str, Any]:
        """Build safe execution environment with allowed libraries"""
        env = {
            # Core libraries
            'pd': pd,
            'np': np,
            'plt': plt,
            'sns': sns,
            'go': go,
            'px': px,
            'math': math,
            'json': json,
            're': re,
            'warnings': warnings,

            # Data
            'df': self.df,

            # Custom helpers
            'st': self._streamlit_mock(),
            'save_plot': self._save_plot_helper,
        }

        # Add optional libraries if available
        if PANDAS_TA_AVAILABLE:
            env['ta'] = ta
        if XGBOOST_AVAILABLE:
            env['xgb'] = xgb
        if SKLEARN_AVAILABLE:
            env['sklearn'] = sklearn
        if STATSMODELS_AVAILABLE:
            env['sm'] = sm
        if SCIPY_AVAILABLE:
            env['scipy'] = scipy
        if POLARS_AVAILABLE:
            env['pl'] = pl
        if ALTAIR_AVAILABLE:
            env['alt'] = alt
        if QUANTSTATS_AVAILABLE:
            env['qs'] = qs
        if MPLFINANCE_AVAILABLE:
            env['mpf'] = mpf

        return env

    def _streamlit_mock(self):
        """Mock Streamlit API for code compatibility"""
        class StreamlitMock:
            @staticmethod
            def write(*args, **kwargs):
                print(" ".join([str(a) for a in args]))

            @staticmethod
            def dataframe(data, **kwargs):
                if isinstance(data, pd.DataFrame):
                    print(data.head(20).to_string())

            @staticmethod
            def table(data, **kwargs):
                if isinstance(data, pd.DataFrame):
                    print(data.to_string())

            @staticmethod
            def plotly_chart(fig, use_container_width=True, **kwargs):
                pass  # We capture figures separately

            @staticmethod
            def pyplot(**kwargs):
                pass  # We capture matplotlib figures

            @staticmethod
            def expander(label):
                class MockExpander:
                    def __enter__(self):
                        return self
                    def __exit__(self, *args):
                        pass
                    @staticmethod
                    def code(text):
                        print(text)
                    @staticmethod
                    def write(*args):
                        print(" ".join([str(a) for a in args]))
                return MockExpander()

            @staticmethod
            def metric(label, value, delta=None):
                print(f"{label}: {value}" + (f" ({delta})" if delta else ""))

            @staticmethod
            def columns(*args):
                # Return list of mock columns
                return [StreamlitMock()] * (args[0] if isinstance(args[0], int) else len(args))

            @staticmethod
            def success(msg):
                print(f"✅ {msg}")

            @staticmethod
            def error(msg):
                print(f"❌ {msg}")

            @staticmethod
            def warning(msg):
                print(f"⚠️ {msg}")

            @staticmethod
            def info(msg):
                print(f"ℹ️ {msg}")

        return StreamlitMock()

    def _save_plot_helper(self, fig=None, format='png'):
        """Helper to save matplotlib/plotly figures"""
        import base64
        from io import BytesIO

        if fig is None:
            # Get current matplotlib figure
            fig = plt.gcf()

        if hasattr(fig, 'to_plotly_json'):
            # It's a plotly figure
            self.figures.append(fig.to_plotly_json())
        else:
            # It's a matplotlib figure
            buf = BytesIO()
            fig.savefig(buf, format=format, bbox_inches='tight', dpi=100)
            buf.seek(0)
            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
            self.plots.append(f"data:image/{format};base64,{img_base64}")
            plt.close(fig)


class TradeSetupDetector:
    """Detects trade setups and actions from AI responses"""

    @staticmethod
    def _repair_json(text: str) -> str:
        """Fix common JSON mistakes"""
        text = re.sub(r'("[\w_]+")\s*:\s*("[^"]*"|-?\d+\.?\d*|true|false|null)\s*\n\s*(")',
                     r'\1: \2,\n  \3', text)
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)
        return text

    @staticmethod
    def detect_trade_setup(text: str) -> Optional[Dict]:
        """Detect TRADE_SETUP JSON block from AI response"""
        json_pattern = r"```json\s*(.*?)\s*```"
        blocks = re.findall(json_pattern, text, re.S | re.I)

        for block in blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
                    return data
            except json.JSONDecodeError:
                try:
                    repaired = TradeSetupDetector._repair_json(block)
                    data = json.loads(repaired)
                    if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
                        return data
                except json.JSONDecodeError:
                    continue

        # Try parsing entire text as JSON
        try:
            data = json.loads(text)
            if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
                return data
        except json.JSONDecodeError:
            try:
                repaired = TradeSetupDetector._repair_json(text)
                data = json.loads(repaired)
                if isinstance(data, dict) and data.get("action") == "TRADE_SETUP":
                    return data
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def detect_trade_action(text: str) -> Optional[Dict]:
        """Detect TRADE_ACTION JSON block from AI response"""
        valid_actions = ["CLOSE_POSITION", "MODIFY_SL", "MODIFY_TP", "MODIFY_SLTP", "ADD_TO_POSITION"]
        json_pattern = r"```json\s*(.*?)\s*```"
        blocks = re.findall(json_pattern, text, re.S | re.I)

        for block in blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict) and data.get("action") in valid_actions:
                    return data
            except json.JSONDecodeError:
                try:
                    repaired = TradeSetupDetector._repair_json(block)
                    data = json.loads(repaired)
                    if isinstance(data, dict) and data.get("action") in valid_actions:
                        return data
                except json.JSONDecodeError:
                    continue

        return None


# Global instances
code_sandbox = None  # Will be set per request with specific DataFrame
trade_detector = TradeSetupDetector()
