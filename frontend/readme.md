# DTU Python Support Survey

A web-based student satisfaction survey and internal problem log for DTU Python Support services.

**Example:** https://www.student.dtu.dk/~s214960/python-support-survey/

## File Structure

```
├── index.html              # Main survey application
├── assets/                 # Satisfaction rating images (face1-5.png)
├── css/                    # Stylesheets (main, sidebar, modal, survey, compact, kiosk)
├── js/                     # JavaScript modules (app, auth, building, config, errors, failsafe, kiosk, problem-log, survey, viewport)
├── partials/               # HTML templates (analytics, building-selection, modals, mode-selection, problem-log, sidebar, survey-form)
├── data/courses.csv        # Course data for autocomplete
└── readme.md               # Documentation
```

## Features

- Form selection screen for supporters (customer satisfaction or internal logging)
- Internal problem log for supporters to record common issues after helping a student
- Building selection interface
- One-time link generation for our Discord help
- QR code generation for static URLs
- Student/Employee role selection
- Satisfaction rating with visual feedback
- Course autocomplete from CSV data
- Analytics dashboard integration with PowerBI
- Kiosk/Tablet Mode: Fullscreen locked mode for public tablet deployment

## Usage

Open `index.html` in a web browser. The application includes:

1. Form Selection: After logging in, supporters choose between Customer Satisfaction and Internal Logging. The sidebar's "Choose form" link returns here.
2. Building Selection: Choose from predefined buildings or enter custom building number (Customer Satisfaction only)
3. Survey Form: Fill out satisfaction survey with student number/DTU credentials
4. Internal Logging: Tick common problems (or describe another one) and submit them to the backend
5. Analytics: View survey statistics (requires authentication)

## Authentication

The application uses password-based authentication for supporters, with automatic bypass for student access:

- Regular Access (`/index.html`): Requires daily access code authentication, then opens the form selection screen
- One-time Links (`?t=TOKEN` or `?token=TOKEN`): Bypass authentication, direct access to survey
- QR Code Access (`?b=BUILDING`): Bypass authentication, direct access to survey

Both one-time links and QR code access automatically enable compact mode for an optimized experience.

Students (one-time links, QR codes and kiosk mode) always go straight to the survey and never see the form selection screen or the internal problem log.

The internal problem log uses the same supporter login as the survey and posts to `/api/problem-logs/` on the Django backend. It has no offline queue: if the backend is unreachable or the session has expired, the form keeps its values and asks the supporter to log in again.

## Architecture

The application uses a modular architecture with:

- Separation of Concerns: CSS, JavaScript, and HTML components are separated into logical modules
- Class-based JavaScript: ES6 classes for better code organization
- Modular CSS: Separate stylesheets for different UI concerns
- Component Templates: Reusable HTML components

## Development

For local development with file:// protocol:
- Use `index.html` with `bundle.js` (pre-bundled JavaScript)
- Components are inlined in the main HTML file

For server deployment:
- Use modular ES6 modules in `js/` directory
- Components can be loaded dynamically from `components/` directory
- Enable HTTP server to avoid CORS restrictions

## Compact Mode

Compact mode is automatically activated when accessing the application via one-time links or QR codes.

### Features

- Navigation Hiding: Automatically hides sidebar, header, and navigation elements
- Tablet Optimization: Optimized spacing, sizing, and touch targets for tablet use
- Focused Experience: Clean, distraction-free interface showing only the survey form
- Authentication Bypass: Skips password requirement for seamless student access

### Implementation

- CSS Styling: `css/compact.css` provides tablet-optimized layouts
- JavaScript Detection: Automatic detection in `js/app.js` and `js/bundle.js`
- Body Class: Adds `compact-mode` class to enable styling when parameters are detected

## Kiosk/Tablet Mode

Kiosk mode provides secure tablet deployment in public spaces.

### Activation

- URL Parameter: Add `?kiosk=1` or `?tablet=1` to the URL
- Toggle Button: Click the floating lock button in the bottom-right corner

### Features

- Fullscreen Mode: Automatically enters fullscreen
- Navigation Hiding: Hides sidebar, header, and navigation elements
- Interaction Blocking: Disables text selection, context menus, and keyboard shortcuts
- Touch Optimization: Larger touch targets and optimized layouts for tablets

### Security Features

- Prevents common keyboard shortcuts (F5, F11, F12, Ctrl+R, etc.)
- Blocks browser navigation and developer tools access
- Disables page refresh and tab switching
  
### Exit Mechanisms for Administrators

- Keyboard Shortcut: Adding "?reset=1" to the website
- Hidden Tap Zone: Click/tap the top-left corner 5 times within 3 seconds
- Temporary Exit Button: A red "Exit Kiosk" button appears after tap activation (auto-hides after 10 seconds)

## Dependencies

- Tailwind CSS (via CDN)
- QR Code generation library (via CDN)
- PowerBI for analytics dashboard
