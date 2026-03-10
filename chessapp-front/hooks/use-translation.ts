import { useLanguage } from '@/app/contexts/LanguageContext';
import { translations } from '@/app/i18n/translations';

export function useTranslation() {
  const { language } = useLanguage();
  return translations[language];
}
