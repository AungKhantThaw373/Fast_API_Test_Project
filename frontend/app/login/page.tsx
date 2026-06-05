'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

// Update this if your backend runs on a different port
const API_BASE_URL = 'http://localhost:8000';

export default function LoginPage() {
    const router = useRouter();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const [showSignUp, setShowSignUp] = useState(false);
    const [signUpData, setSignUpData] = useState({
        username: '',
        email: '',
        password: '',
    });
    const [signUpError, setSignUpError] = useState('');
    const [signUpLoading, setSignUpLoading] = useState(false);

    useEffect(() => {
        // Quick check to see if we already have a valid session via the HTTPOnly cookie
        const checkAuth = async () => {
            try {
                const res = await fetch(`${API_BASE_URL}/me`, { credentials: 'include' });
                if (res.ok) {
                    router.push('/dashboard'); // Already logged in
                }
            } catch (err) {
                // Ignore error, user just needs to log in
            }
        };
        checkAuth();
    }, [router]);

    const handleLogin = async (e: React.SubmitEvent<HTMLFormElement>) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        try {
            // OAuth2PasswordRequestForm expects form-urlencoded data
            const formData = new URLSearchParams();
            formData.append('username', email); // Backend maps email to 'username' in the form
            formData.append('password', password);

            const response = await fetch(`${API_BASE_URL}/token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData,
                credentials: 'include', // Important: receives the HttpOnly cookie
            });

            if (response.ok) {
                router.push('/dashboard');
            } else {
                const data = await response.json();
                setError(data.detail || 'Invalid credentials');
            }
        } catch (err) {
            setError('Network error. Is the server running?');
        } finally {
            setLoading(false);
        }
    };

    const handleSignUp = async (e: React.SubmitEvent<HTMLFormElement>) => {
        e.preventDefault();
        setSignUpLoading(true);
        setSignUpError('');

        try {
            const response = await fetch(`${API_BASE_URL}/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(signUpData),
            });

            if (response.ok) {
                // Success: Switch to login view and pre-fill the email
                setShowSignUp(false);
                setEmail(signUpData.email);
                setPassword('');
            } else {
                const data = await response.json();
                setSignUpError(data.detail || 'Sign up failed');
            }
        } catch (err) {
            setSignUpError('Network error. Is the server running?');
        } finally {
            setSignUpLoading(false);
        }
    };

    return (
        <div style={styles.container}>
            <div style={styles.box}>
                <h1 style={styles.title}>{showSignUp ? 'Sign Up' : 'Login'}</h1>

                {!showSignUp ? (
                    // Login Form
                    <form onSubmit={handleLogin} style={styles.form}>
                        {error && <div style={styles.error}>{error}</div>}

                        <div style={styles.formGroup}>
                            <label style={styles.label}>Email</label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                required
                                style={styles.input}
                                placeholder="Enter your email"
                            />
                        </div>

                        <div style={styles.formGroup}>
                            <label style={styles.label}>Password</label>
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                required
                                style={styles.input}
                                placeholder="Enter your password"
                            />
                        </div>

                        <button type="submit" disabled={loading} style={styles.button}>
                            {loading ? 'Logging in...' : 'Login'}
                        </button>

                        <p style={styles.switchText}>
                            Don't have an account?{' '}
                            <button
                                type="button"
                                onClick={() => setShowSignUp(true)}
                                style={styles.switchLink}
                            >
                                Sign up
                            </button>
                        </p>
                    </form>
                ) : (
                    // Sign Up Form
                    <form onSubmit={handleSignUp} style={styles.form}>
                        {signUpError && <div style={styles.error}>{signUpError}</div>}

                        <div style={styles.formGroup}>
                            <label style={styles.label}>Username</label>
                            <input
                                type="text"
                                value={signUpData.username}
                                onChange={(e) =>
                                    setSignUpData({ ...signUpData, username: e.target.value })
                                }
                                required
                                style={styles.input}
                                placeholder="Choose a username"
                            />
                        </div>

                        <div style={styles.formGroup}>
                            <label style={styles.label}>Email</label>
                            <input
                                type="email"
                                value={signUpData.email}
                                onChange={(e) =>
                                    setSignUpData({ ...signUpData, email: e.target.value })
                                }
                                required
                                style={styles.input}
                                placeholder="Enter your email"
                            />
                        </div>

                        <div style={styles.formGroup}>
                            <label style={styles.label}>Password</label>
                            <input
                                type="password"
                                value={signUpData.password}
                                onChange={(e) =>
                                    setSignUpData({ ...signUpData, password: e.target.value })
                                }
                                required
                                style={styles.input}
                                placeholder="Enter a password"
                            />
                        </div>

                        <button type="submit" disabled={signUpLoading} style={styles.button}>
                            {signUpLoading ? 'Creating account...' : 'Sign Up'}
                        </button>

                        <p style={styles.switchText}>
                            Already have an account?{' '}
                            <button
                                type="button"
                                onClick={() => setShowSignUp(false)}
                                style={styles.switchLink}
                            >
                                Login
                            </button>
                        </p>
                    </form>
                )}
            </div>
        </div>
    );
}

const styles = {
    container: {
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        backgroundColor: '#f5f5f5',
        fontFamily: 'Arial, sans-serif',
    },
    box: {
        backgroundColor: 'white',
        padding: '40px',
        borderRadius: '8px',
        boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
        width: '100%',
        maxWidth: '400px',
    },
    title: {
        margin: '0 0 20px 0',
        fontSize: '24px',
        color: '#333',
        textAlign: 'center' as const,
    },
    form: {
        display: 'flex',
        flexDirection: 'column' as const,
        gap: '15px',
    },
    formGroup: {
        display: 'flex',
        flexDirection: 'column' as const,
        gap: '5px',
    },
    label: {
        fontSize: '14px',
        color: '#666',
        fontWeight: 'bold' as const,
    },
    input: {
        padding: '10px',
        fontSize: '14px',
        color: 'black',
        border: '1px solid #ddd',
        borderRadius: '4px',
        outline: 'none',
    },
    button: {
        padding: '12px',
        fontSize: '16px',
        fontWeight: 'bold' as const,
        color: 'white',
        backgroundColor: '#0070f3',
        border: 'none',
        borderRadius: '4px',
        cursor: 'pointer',
        marginTop: '10px',
    },
    error: {
        padding: '10px',
        backgroundColor: '#f8d7da',
        color: '#721c24',
        borderRadius: '4px',
        fontSize: '14px',
        border: '1px solid #f5c6cb',
    },
    switchText: {
        margin: '15px 0 0 0',
        fontSize: '14px',
        color: '#666',
        textAlign: 'center' as const,
    },
    switchLink: {
        background: 'none',
        border: 'none',
        color: '#0070f3',
        textDecoration: 'underline',
        cursor: 'pointer',
        padding: 0,
        fontSize: '14px',
    },
};
