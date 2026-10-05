"use client";

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { getAuthToken, API_BASE_URL } from '@/lib/api';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle, AlertCircle, Search, Mail, ArrowRight } from 'lucide-react';

export default function ComplaintPage() {
  const { user, fetchUser } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [claim, setClaim] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [draft, setDraft] = useState('');
  const [complaintId, setComplaintId] = useState<number | null>(null);
  const [contactEmail, setContactEmail] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [contactType, setContactType] = useState('');
  const [contactSourceUrl, setContactSourceUrl] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [success, setSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [isRetryableError, setIsRetryableError] = useState(false);

  useEffect(() => {
    const claimParam = searchParams.get('claim');
    if (claimParam) setClaim(claimParam);
  }, [searchParams]);

  const handleVerifySource = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!sourceUrl || !claim) return;

    setIsVerifying(true);
    setErrorMsg('');
    setIsRetryableError(false);
    setDraft('');
    setComplaintId(null);

    try {
      const token = getAuthToken();
      const res = await fetch(`${API_BASE_URL}/complaints/verify-source`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ claim, url: sourceUrl }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        // Graceful degradation for temporary AI/provider outages.
        if (res.status === 503) {
          const detail = data?.detail;
          const message =
            typeof detail === 'object'
              ? detail?.message
              : detail;

          setIsRetryableError(true);
          setErrorMsg(
            message ||
            'Source verification is temporarily unavailable because the AI verification service is busy. Please try again in a moment. No complaint was created and no GEM was awarded.'
          );
          return;
        }

        const detail = data?.detail;
        setErrorMsg(
          typeof detail === 'object'
            ? detail?.message || 'Failed to verify source.'
            : detail || 'Failed to verify source.'
        );
        return;
      }

      if (data.match) {
        setDraft(data.draft || '');
        setComplaintId(data.complaint_id || null);
        setContactEmail(data.contact_email || '');
        setContactPhone(data.contact_phone || '');
        setContactType(data.contact_type || '');
        setContactSourceUrl(data.contact_source_url || '');
      } else {
        setErrorMsg(data.message || 'The source could not be verified.');
        setContactPhone(data.contact_phone || '');
        setContactType(data.contact_type || '');
        setContactSourceUrl(data.contact_source_url || '');
      }
    } catch (err: any) {
      setIsRetryableError(true);
      setErrorMsg(
        'The source verification service could not be reached. Please check your connection and try again. No complaint was created and no GEM was awarded.'
      );
    } finally {
      setIsVerifying(false);
    }
  };

  const handleSend = async () => {
    if (!complaintId || !draft) return;
    setIsSending(true);
    setErrorMsg('');
    setIsRetryableError(false);

    try {
      const token = getAuthToken();
      const res = await fetch(`${API_BASE_URL}/complaints/send`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ complaint_id: complaintId, draft }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to send complaint.');

      if (data.success) {
        await fetchUser();
        setSuccess(true);
      } else {
        setErrorMsg(data.message || 'Complaint was not sent.');
      }
    } catch (err: any) {
      setErrorMsg(
        'The complaint could not be sent. Please try again. No GEM was awarded unless the email was successfully dispatched.'
      );
    } finally {
      setIsSending(false);
    }
  };

  if (success) {
    return (
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="max-w-2xl mx-auto mt-12 bg-white p-10 rounded-2xl shadow-lg border border-green-100 text-center relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-2 bg-gradient-to-r from-green-400 to-emerald-500"></div>
        <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 200, delay: 0.1 }} className="text-green-500 mb-6 flex justify-center">
          <CheckCircle size={64} strokeWidth={1.5} />
        </motion.div>
        <h1 className="text-3xl font-extrabold text-gray-900 mb-3 tracking-tight">Complaint Dispatched!</h1>
        <p className="text-gray-600 mb-2 text-lg">The complaint email was successfully sent to the discovered publisher contact.</p>
        <p className="text-green-700 font-semibold mb-8">+1 GEM awarded.</p>
        <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={() => router.push('/')} className="bg-green-600 text-white font-medium py-3 px-8 rounded-lg hover:bg-green-700 shadow-md transition-colors inline-flex items-center gap-2">
          Return Home <ArrowRight size={18} />
        </motion.button>
      </motion.div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-white p-8 rounded-2xl shadow-sm border border-gray-100">
        <h1 className="text-2xl font-extrabold text-slate-900 mb-2 tracking-tight">File a Misinformation Complaint</h1>
        <p className="text-slate-600 mb-8 leading-relaxed">We verify the source, find a publisher contact through web search, and prepare a draft for your review.</p>

        <form onSubmit={handleVerifySource} className="space-y-6">
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-2">Claim to dispute</label>
            <textarea required value={claim} onChange={e => setClaim(e.target.value)} disabled={isVerifying || !!draft} className="w-full px-4 py-3 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 bg-slate-50 min-h-[80px]" />
          </div>
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-2">Source URL (where you found the claim)</label>
            <input type="url" required placeholder="https://example.com/fake-news-article" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} disabled={isVerifying || !!draft} className="w-full px-4 py-3 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 bg-white" />
          </div>

          <AnimatePresence>
            {errorMsg && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="bg-red-50 text-red-700 px-4 py-3 rounded-lg flex items-start gap-3 border border-red-100 overflow-hidden">
                <AlertCircle className="shrink-0 mt-0.5" size={18} />
                <div className="flex-1">
                  <p className="text-sm font-medium">{errorMsg}</p>
                  {isRetryableError && !draft && (
                    <button
                      type="button"
                      onClick={() => handleVerifySource()}
                      disabled={isVerifying}
                      className="mt-3 inline-flex items-center rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                    >
                      {isVerifying ? 'Retrying...' : 'Try Again'}
                    </button>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {!draft && (
            <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }} type="submit" disabled={isVerifying || !sourceUrl || !claim} className="w-full bg-indigo-600 text-white font-medium py-3 px-4 rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-all shadow-md flex justify-center items-center gap-2">
              {isVerifying ? <><div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full"></div> Verifying source & finding publisher contact...</> : <><Search size={18} /> Verify Source & Find Publisher Contact</>}
            </motion.button>
          )}
        </form>
      </motion.div>

      <AnimatePresence>
        {draft && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-white p-8 rounded-2xl shadow-md border border-indigo-100 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-indigo-500"></div>
            <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2"><Mail className="text-indigo-500" size={24} /> Review & Edit Draft</h2>

            <div className="mb-5 bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-700">
              <p><strong>Publisher contact:</strong> {contactEmail}</p>
              {contactType && <p><strong>Contact type:</strong> {contactType}</p>}
              {contactPhone && <p><strong>Phone:</strong> {contactPhone}</p>}
              {contactSourceUrl && <p className="mt-1 break-all"><strong>Contact source:</strong> {contactSourceUrl}</p>}
            </div>

            <textarea value={draft} onChange={e => setDraft(e.target.value)} className="w-full h-72 p-5 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-6 text-sm font-mono text-slate-800 bg-slate-50 leading-relaxed shadow-inner" />
            <div className="flex justify-end gap-3">
              <button onClick={() => { setDraft(''); setComplaintId(null); }} className="px-5 py-2.5 font-medium text-slate-600 rounded-lg hover:bg-slate-100 transition-colors">Cancel</button>
              <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={handleSend} disabled={isSending || !complaintId} className="bg-indigo-600 text-white font-medium py-2.5 px-6 rounded-lg hover:bg-indigo-700 disabled:opacity-50 shadow-md transition-all flex items-center gap-2">
                {isSending ? <><div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full"></div> Sending...</> : 'Confirm & Dispatch Email'}
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
