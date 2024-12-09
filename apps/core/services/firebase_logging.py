# apps/core/services/firebase_logging.py
import logging
import functools
import time
import traceback
from datetime import datetime
from typing import Any, Callable, Dict, Optional
import json

class FirebaseLogger:
    def __init__(self):
        self.logger = logging.getLogger('firebase.operations')
        self._setup_logger()
    
    def _setup_logger(self):
        """Configure detailed logging for Firebase operations"""
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s\n'
            'Additional Info: %(extra_info)s\n'
            'Duration: %(duration).2fms\n'
            '%(stack_trace)s'
        )
        
        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # File Handler for detailed logs
        file_handler = logging.FileHandler('logs/firebase_detailed.log')
        file_handler.setFormatter(formatter)
        
        # Error File Handler
        error_handler = logging.FileHandler('logs/firebase_errors.log')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(error_handler)
        self.logger.setLevel(logging.DEBUG)

    def log_operation(self, 
                     operation_name: str, 
                     success: bool, 
                     duration: float,
                     extra_info: Dict = None,
                     error: Optional[Exception] = None):
        """Log Firebase operation with detailed information"""
        log_data = {
            'extra_info': json.dumps(extra_info or {}),
            'duration': duration * 1000,  # Convert to milliseconds
            'stack_trace': ''
        }
        
        if error:
            log_data['stack_trace'] = f"Error Stack:\n{traceback.format_exc()}"
            self.logger.error(
                f"Firebase operation '{operation_name}' failed",
                extra=log_data
            )
        else:
            self.logger.info(
                f"Firebase operation '{operation_name}' completed successfully",
                extra=log_data
            )

def firebase_operation_logger(operation_name: str):
    """Decorator for logging Firebase operations"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            logger = FirebaseLogger()
            start_time = time.time()
            error = None
            result = None
            
            try:
                # Extract relevant information for logging
                extra_info = {
                    'operation': operation_name,
                    'args': str(args),
                    'kwargs': str(kwargs),
                    'timestamp': datetime.now().isoformat()
                }
                
                # Execute the operation
                result = await func(*args, **kwargs)
                
                # Add result summary to logging info
                if result:
                    if isinstance(result, dict):
                        extra_info['result_summary'] = {
                            k: str(v)[:100] for k, v in result.items()
                        }
                    else:
                        extra_info['result_summary'] = str(result)[:100]
                
                return result
                
            except Exception as e:
                error = e
                extra_info = {
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                }
                raise
                
            finally:
                duration = time.time() - start_time
                logger.log_operation(
                    operation_name=operation_name,
                    success=error is None,
                    duration=duration,
                    extra_info=extra_info,
                    error=error
                )
                
        return wrapper
    return decorator