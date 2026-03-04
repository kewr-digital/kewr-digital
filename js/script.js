document.addEventListener('DOMContentLoaded', () => {
    // Initialize Lucide Icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // Mobile Menu Toggle
    const mobileMenuButton = document.getElementById('mobile-menu-button');
    const mobileMenu = document.getElementById('mobile-menu');
    if (mobileMenuButton && mobileMenu) {
        mobileMenuButton.addEventListener('click', () => {
            mobileMenu.classList.toggle('hidden');
            const menuIcon = mobileMenuButton.querySelector('[data-lucide="menu"]');
            const xIcon = mobileMenuButton.querySelector('[data-lucide="x"]');
            if (menuIcon && xIcon) {
                menuIcon.classList.toggle('hidden');
                xIcon.classList.toggle('hidden');
                // Re-init icons to handle visibility change if needed
                lucide.createIcons();
            }
        });
    }

    // Modal Control Utility
    const toggleModal = (modalId, show) => {
        const modal = document.getElementById(modalId);
        if (modal) {
            if (show) {
                modal.classList.remove('hidden');
                document.body.style.overflow = 'hidden';
            } else {
                modal.classList.add('hidden');
                document.body.style.overflow = 'auto';
            }
        }
    };

    // Language Switcher Logic (i18n)
    const langSwitcher = document.getElementById('lang-switcher');
    const langText = document.getElementById('lang-text');
    let translations = {};
    let currentLang = 'EN';

    const applyTranslations = (lang) => {
        currentLang = lang.toUpperCase();
        if (langText) langText.textContent = currentLang;
        
        // Update localStorage
        localStorage.setItem('locale', currentLang);
        localStorage.setItem('locale_expiry', Date.now() + 24 * 60 * 60 * 1000);

        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (translations[key] && translations[key][lang.toLowerCase()]) {
                const translation = translations[key][lang.toLowerCase()];
                if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                    el.setAttribute('placeholder', translation);
                } else {
                    el.textContent = translation;
                }
            }
        });
        console.log(`Language applied: ${currentLang}`);
    };

    const initLanguage = async () => {
        try {
            // Load translations
            const langResponse = await fetch('languages.json');
            translations = await langResponse.json();

            // Check cache
            const cachedLocale = localStorage.getItem('locale');
            const expiry = localStorage.getItem('locale_expiry');
            
            if (cachedLocale && expiry && Date.now() < parseInt(expiry)) {
                console.log(`Using cached locale: ${cachedLocale}`);
                applyTranslations(cachedLocale);
                return;
            }

            // Detect country via IP
            const ipResponse = await fetch('https://ipapi.co/json/');
            const ipData = await ipResponse.json();
            
            const detectLang = ipData.country_code === 'ID' ? 'ID' : 'EN';
            applyTranslations(detectLang);
        } catch (error) {
            console.error('Initialization failed:', error);
            // Fallback if fetch fails
            if (Object.keys(translations).length > 0) applyTranslations('EN');
        }
    };

    if (langSwitcher) {
        langSwitcher.addEventListener('click', () => {
            const nextLang = currentLang === 'EN' ? 'ID' : 'EN';
            applyTranslations(nextLang);
        });
        initLanguage();
    }

    // Consultation Modal
    document.querySelectorAll('.open-consultation').forEach(button => {
        button.addEventListener('click', () => toggleModal('consultation-modal', true));
    });

    // Close Modals
    document.querySelectorAll('.modal-close').forEach(closeEl => {
        closeEl.addEventListener('click', (e) => {
            // Check if it's the backdrop or the close button
            const modal = e.target.closest('[id$="-modal"]');
            if (modal && (e.target.classList.contains('modal-close') || e.target.textContent === '×')) {
                toggleModal(modal.id, false);
            }
        });
    });

    // Close on escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const openModal = document.querySelector('[id$="-modal"]:not(.hidden)');
            if (openModal) toggleModal(openModal.id, false);
        }
    });

    // WhatsApp logic
    const sendWhatsApp = document.getElementById('send-whatsapp');
    const whatsappMessage = document.getElementById('whatsapp-message');
    if (sendWhatsApp && whatsappMessage) {
        sendWhatsApp.addEventListener('click', () => {
            const messageText = whatsappMessage.value.trim() || "Hello, I'm interested in a consultation.";
            const message = encodeURIComponent(messageText);
            window.open(`https://wa.me/6282221213199?text=${message}`, '_blank');
            toggleModal('consultation-modal', false);
            whatsappMessage.value = '';
        });
    }

    // FAQ Accordion
    document.querySelectorAll('.faq-button').forEach(button => {
        button.addEventListener('click', () => {
            const answer = button.nextElementSibling;
            const icon = button.querySelector('.faq-icon');
            const isOpen = !answer.classList.contains('hidden');
            
            // Close all other FAQs
            document.querySelectorAll('.faq-answer').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('.faq-icon').forEach(el => el.textContent = '+');

            if (!isOpen) {
                answer.classList.remove('hidden');
                icon.textContent = '-';
            }
        });
    });

    // Service Card Learn More
    document.querySelectorAll('.service-card').forEach(card => {
        const learnMoreBtn = card.querySelector('.learn-more');
        const featuresList = card.querySelector('.features-list');
        if (learnMoreBtn && featuresList) {
            learnMoreBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                featuresList.classList.toggle('hidden');
                const isHidden = featuresList.classList.contains('hidden');
                const btnKey = isHidden ? 'btn_learn_more' : 'btn_show_less';
                learnMoreBtn.setAttribute('data-i18n', btnKey);
                if (translations[btnKey]) {
                    learnMoreBtn.textContent = translations[btnKey][currentLang.toLowerCase()];
                }
            });
        }
    });

    // Smooth scroll for anchors
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href.startsWith('#')) {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth'
                    });
                }
            }
        });
    });
});