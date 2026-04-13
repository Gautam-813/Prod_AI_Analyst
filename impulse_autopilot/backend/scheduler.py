"""
APScheduler Integration for Autopilot
Manages background scheduling with persistent job state
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone
from typing import Optional

from database import SessionLocal
from models import AutopilotConfig, AutopilotLog
from autopilot import AutopilotEngine


class AutopilotScheduler:
    """Manages the autopilot background scheduler"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.is_running = False
    
    def start(self):
        """Start the scheduler system"""
        if not self.is_running:
            self.scheduler.start()
            self.is_running = True
            print("✅ Scheduler system started")
    
    def stop(self):
        """Stop the scheduler system"""
        if self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            print("⏹️ Scheduler system stopped")
    
    def load_and_schedule_autopilot(self):
        """Load config from DB and schedule autopilot job if enabled"""
        db = SessionLocal()
        try:
            config = db.query(AutopilotConfig).first()
            if not config:
                print("⚠️ No autopilot configuration found - autopilot will not run")
                print("ℹ️ Configure autopilot via dashboard settings")
                return False

            if config.enabled:
                # Remove existing job if any
                if self.scheduler.get_job("autopilot_job"):
                    self.scheduler.remove_job("autopilot_job")

                # Add new job with configured interval
                self.scheduler.add_job(
                    func=self._execute_autopilot_cycle,
                    trigger=IntervalTrigger(seconds=config.interval_seconds),
                    id="autopilot_job",
                    name="Autopilot Trading Cycle",
                    replace_existing=True,
                    max_instances=1  # Prevent overlapping executions
                )

                # Update next run time in DB
                job = self.scheduler.get_job("autopilot_job")
                if job:
                    config.next_run_timestamp = job.next_run_time

                    # Log startup
                    log = AutopilotLog(
                        timestamp=datetime.now(timezone.utc),
                        level="INFO",
                        message=f"🟢 Autopilot started - Running every {config.interval_seconds}s ({config.interval_seconds/60:.0f} min)"
                    )
                    db.add(log)
                    db.commit()

                print(f"✅ Autopilot scheduled - Every {config.interval_seconds}s")
                return True
            else:
                # Remove job if disabled
                if self.scheduler.get_job("autopilot_job"):
                    self.scheduler.remove_job("autopilot_job")
                    print("⏹️ Autopilot disabled - Job removed")
                print("ℹ️ Autopilot is disabled - enable via dashboard to start trading")
                return False

        except Exception as e:
            print(f"❌ Error scheduling autopilot: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            db.close()
    
    def _execute_autopilot_cycle(self):
        """Execute one autopilot cycle (called by scheduler)"""
        db = SessionLocal()
        try:
            print(f"\n{'='*60}")
            print(f"🤖 AUTOPILOT CYCLE - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"{'='*60}")
            
            # Update last run timestamp
            config = db.query(AutopilotConfig).first()
            if config:
                config.last_run_timestamp = datetime.now(timezone.utc)
                db.commit()
            
            # Execute cycle
            engine = AutopilotEngine(db_session=db)
            result = engine.execute_cycle()
            
            # Log result summary
            if result.get("success"):
                print(f"✅ Autopilot cycle completed - Trade placed: #{result['details'].get('ticket', 'N/A')}")
            else:
                if result.get("trade_placed"):
                    print(f"⚠️ Autopilot cycle completed - No trade setup identified")
                else:
                    print(f"❌ Autopilot cycle failed - {result.get('details', {}).get('error', 'Unknown error')}")
            
        except Exception as e:
            print(f"❌ Autopilot cycle error: {e}")
            
            # Log error
            try:
                log = AutopilotLog(
                    timestamp=datetime.now(timezone.utc),
                    level="CRITICAL",
                    message=f"Autopilot cycle error: {str(e)}"
                )
                db.add(log)
                db.commit()
            except:
                pass
        finally:
            db.close()
    
    def enable_autopilot(self) -> dict:
        """Enable autopilot and start scheduling"""
        db = SessionLocal()
        try:
            config = db.query(AutopilotConfig).first()
            if not config:
                return {"success": False, "error": "No configuration found"}
            
            config.enabled = True
            db.commit()
            
            success = self.load_and_schedule_autopilot()
            
            if success:
                return {
                    "success": True,
                    "message": f"Autopilot enabled - Running every {config.interval_seconds}s",
                    "interval_seconds": config.interval_seconds,
                    "next_run": config.next_run_timestamp.isoformat() if config.next_run_timestamp else None
                }
            else:
                return {"success": False, "error": "Failed to schedule autopilot"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            db.close()
    
    def disable_autopilot(self) -> dict:
        """Disable autopilot and stop scheduling"""
        db = SessionLocal()
        try:
            config = db.query(AutopilotConfig).first()
            if not config:
                return {"success": False, "error": "No configuration found"}
            
            config.enabled = False
            config.next_run_timestamp = None
            db.commit()
            
            # Remove job
            if self.scheduler.get_job("autopilot_job"):
                self.scheduler.remove_job("autopilot_job")
            
            # Log
            log = AutopilotLog(
                timestamp=datetime.now(timezone.utc),
                level="INFO",
                message="🔴 Autopilot disabled by user"
            )
            db.add(log)
            db.commit()
            
            return {"success": True, "message": "Autopilot disabled"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            db.close()
    
    def update_interval(self, interval_seconds: int) -> dict:
        """Update autopilot interval and reschedule"""
        db = SessionLocal()
        try:
            config = db.query(AutopilotConfig).first()
            if not config:
                return {"success": False, "error": "No configuration found"}
            
            if interval_seconds < 60:
                return {"success": False, "error": "Interval must be at least 60 seconds"}
            
            old_interval = config.interval_seconds
            config.interval_seconds = interval_seconds
            db.commit()
            
            # If currently enabled, reschedule
            if config.enabled:
                success = self.load_and_schedule_autopilot()
                if success:
                    return {
                        "success": True,
                        "message": f"Interval updated: {old_interval}s → {interval_seconds}s",
                        "interval_seconds": interval_seconds
                    }
                else:
                    return {"success": False, "error": "Failed to reschedule with new interval"}
            else:
                return {
                    "success": True,
                    "message": f"Interval updated: {old_interval}s → {interval_seconds}s (will apply when enabled)",
                    "interval_seconds": interval_seconds
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            db.close()
    
    def get_status(self) -> dict:
        """Get current scheduler status"""
        db = SessionLocal()
        try:
            config = db.query(AutopilotConfig).first()
            if not config:
                return {"error": "No configuration found"}
            
            job = self.scheduler.get_job("autopilot_job")
            
            return {
                "enabled": config.enabled,
                "scheduler_running": self.is_running,
                "job_scheduled": job is not None,
                "interval_seconds": config.interval_seconds,
                "interval_minutes": config.interval_seconds / 60,
                "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
                "last_run": config.last_run_timestamp.isoformat() if config.last_run_timestamp else None,
                "success_count": config.success_count,
                "error_count": config.error_count,
                "lot_size": config.lot_size,
                "symbol": config.symbol
            }
            
        except Exception as e:
            return {"error": str(e)}
        finally:
            db.close()


# Global scheduler instance
scheduler = AutopilotScheduler()
