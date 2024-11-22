// src/services/authService.js

const API_URL = 'http://localhost:8000/api/users/';

class AuthService {
    async register(username, email, password, password2, firstName, lastName) {
        const response = await fetch(`${API_URL}register/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                username,
                email,
                password,
                password2,
                first_name: firstName,
                last_name: lastName
            }),
        });
        const data = await response.json();
        if (response.ok) {
            localStorage.setItem('user', JSON.stringify(data.user));
            localStorage.setItem('tokens', JSON.stringify(data.tokens));
        }
        return data;
    }

    async login(username, password) {
        const response = await fetch(`${API_URL}token/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, password }),
        });
        const data = await response.json();
        if (response.ok) {
            localStorage.setItem('user', JSON.stringify(data.user));
            localStorage.setItem('tokens', JSON.stringify({
                access: data.access,
                refresh: data.refresh
            }));
        }
        return data;
    }

    logout() {
        const tokens = JSON.parse(localStorage.getItem('tokens'));
        if (tokens?.refresh) {
            fetch(`${API_URL}logout/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${tokens.access}`
                },
                body: JSON.stringify({ refresh_token: tokens.refresh }),
            });
        }
        localStorage.removeItem('user');
        localStorage.removeItem('tokens');
    }

    getCurrentUser() {
        return JSON.parse(localStorage.getItem('user'));
    }

    async updateProfile(profileData) {
        const tokens = JSON.parse(localStorage.getItem('tokens'));
        const response = await fetch(`${API_URL}profile/`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${tokens.access}`
            },
            body: JSON.stringify(profileData),
        });
        return await response.json();
    }

    async changePassword(currentPassword, newPassword, newPassword2) {
        const tokens = JSON.parse(localStorage.getItem('tokens'));
        const response = await fetch(`${API_URL}change-password/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${tokens.access}`
            },
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword,
                new_password2: newPassword2
            }),
        });
        return await response.json();
    }

    // Helper method to get the authentication header
    getAuthHeader() {
        const tokens = JSON.parse(localStorage.getItem('tokens'));
        if (tokens?.access) {
            return { 'Authorization': `Bearer ${tokens.access}` };
        }
        return {};
    }
}

export default new AuthService();
