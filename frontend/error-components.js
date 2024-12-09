// src/components/ErrorBoundary.js
import React from 'react';

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true };
    }

    componentDidCatch(error, errorInfo) {
        this.setState({
            error: error,
            errorInfo: errorInfo
        });
        // You can also log the error to an error reporting service here
        console.error('Error caught by boundary:', error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="min-h-screen flex items-center justify-center bg-gray-50">
                    <div className="max-w-md w-full space-y-8 p-6">
                        <div className="text-center">
                            <h2 className="text-2xl font-bold text-gray-900 mb-4">
                                Something went wrong
                            </h2>
                            <p className="text-gray-600 mb-4">
                                We're sorry! The application encountered an unexpected error.
                            </p>
                            <button
                                onClick={() => window.location.reload()}
                                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md"
                            >
                                Reload Page
                            </button>
                        </div>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}

// src/components/ErrorAlert.js
const ErrorAlert = ({ message, onClose }) => {
    return (
        <div className="fixed bottom-4 right-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
            <strong className="font-bold">Error! </strong>
            <span className="block sm:inline">{message}</span>
            {onClose && (
                <button
                    className="absolute top-0 bottom-0 right-0 px-4 py-3"
                    onClick={onClose}
                >
                    <span className="text-2xl">&times;</span>
                </button>
            )}
        </div>
    );
};

export { ErrorBoundary, ErrorAlert };
