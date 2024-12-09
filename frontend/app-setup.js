// src/App.js
import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Login from './components/Login';
import Register from './components/Register';
import Profile from './components/Profile';
import Dashboard from './components/Dashboard';
import NavBar from './components/NavBar';

const App = () => {
    return (
        <AuthProvider>
            <Router>
                <div className="min-h-screen bg-gray-100">
                    <NavBar />
                    <Routes>
                        <Route path="/login" element={<Login />} />
                        <Route path="/register" element={<Register />} />
                        <Route 
                            path="/profile" 
                            element={
                                <ProtectedRoute>
                                    <Profile />
                                </ProtectedRoute>
                            } 
                        />
                        <Route 
                            path="/dashboard" 
                            element={
                                <ProtectedRoute>
                                    <Dashboard />
                                </ProtectedRoute>
                            } 
                        />
                        <Route path="/" element={<Navigate to="/dashboard" replace />} />
                    </Routes>
                </div>
            </Router>
        </AuthProvider>
    );
};

export default App;

// src/components/NavBar.js
import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import