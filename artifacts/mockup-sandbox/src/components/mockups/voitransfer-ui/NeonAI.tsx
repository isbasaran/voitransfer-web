import React, { useState } from 'react';
import { Send, MapPin, Calendar, Clock, Plane, CreditCard, ChevronRight, Sparkles, CheckCircle2, Ticket } from 'lucide-react';

type TabType = 'yeni' | 'sorgula' | 'duzenle' | 'iptal';

export function NeonAI() {
  const [activeTab, setActiveTab] = useState<TabType>('yeni');
  const [inputValue, setInputValue] = useState('');
  const [showSummary, setShowSummary] = useState(true);

  const tabs = [
    { id: 'yeni', label: 'YENİ REZERVASYON' },
    { id: 'sorgula', label: 'SORGULA' },
    { id: 'duzenle', label: 'DÜZENLE' },
    { id: 'iptal', label: 'İPTAL' },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-teal-400 via-blue-500 to-indigo-600 p-4 md:p-8 flex items-center justify-center font-sans antialiased">
      {/* Main Container */}
      <div className="w-full max-w-5xl bg-white/95 backdrop-blur-xl rounded-3xl shadow-[0_20px_50px_rgba(8,_112,_184,_0.7)] border border-white/20 overflow-hidden flex flex-col md:flex-row h-[85vh] min-h-[700px]">
        
        {/* Left/Top Sidebar - Branding & Tabs */}
        <div className="w-full md:w-80 bg-gradient-to-b from-indigo-50/50 to-white border-b md:border-b-0 md:border-r border-indigo-100 p-6 flex flex-col shrink-0">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-teal-400 to-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-200">
              <Sparkles className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-black bg-clip-text text-transparent bg-gradient-to-r from-teal-600 to-indigo-600">
                VoiTransfer AI
              </h1>
              <p className="text-xs font-medium text-indigo-400 tracking-wider">AKILLI ASİSTAN</p>
            </div>
          </div>

          <div className="flex-1">
            <h2 className="text-sm font-semibold text-slate-400 mb-4 px-2 uppercase tracking-wider">İşlemler</h2>
            <div className="flex flex-row md:flex-col gap-2 overflow-x-auto md:overflow-visible pb-2 md:pb-0 scrollbar-hide">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as TabType)}
                  className={`
                    flex items-center justify-between px-4 py-3.5 rounded-2xl text-sm font-bold transition-all duration-300 ease-out whitespace-nowrap
                    ${activeTab === tab.id 
                      ? 'bg-gradient-to-r from-teal-400 to-indigo-500 text-white shadow-md shadow-indigo-200 translate-x-1' 
                      : 'bg-white text-slate-500 hover:bg-indigo-50/50 hover:text-indigo-600 border border-slate-100'
                    }
                  `}
                >
                  {tab.label}
                  {activeTab === tab.id && <ChevronRight className="w-4 h-4 opacity-70" />}
                </button>
              ))}
            </div>
          </div>

          <div className="hidden md:block mt-auto p-4 rounded-2xl bg-indigo-50 border border-indigo-100/50">
            <p className="text-xs text-indigo-800/70 font-medium leading-relaxed">
              VoiTransfer AI ile saniyeler içinde transfer işlemlerinizi yönetin.
            </p>
          </div>
        </div>

        {/* Right Area - Chat & Summary */}
        <div className="flex-1 flex flex-col relative bg-slate-50/50">
          
          {/* Header */}
          <div className="h-16 border-b border-indigo-100/50 bg-white/50 backdrop-blur-sm flex items-center px-6 sticky top-0 z-10">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-teal-400 animate-pulse"></span>
              <span className="text-sm font-semibold text-slate-700">Asistan Çevrimiçi</span>
            </div>
          </div>

          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-hide">
            
            {/* AI Message */}
            <div className="flex gap-4 max-w-[85%]">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-teal-100 to-indigo-100 flex items-center justify-center shrink-0 border border-indigo-50">
                <Sparkles className="w-5 h-5 text-indigo-600" />
              </div>
              <div className="bg-white p-4 rounded-3xl rounded-tl-sm shadow-sm border border-slate-100 text-slate-700 text-sm leading-relaxed">
                <p>Merhaba! Ben VoiTransfer AI. Size Antalya Havalimanı transferiniz için nasıl yardımcı olabilirim?</p>
                <p className="mt-2 text-slate-500 text-xs">Uçuş numaranızı ve kişi sayısını belirterek başlayabilirsiniz.</p>
              </div>
            </div>

            {/* User Message */}
            <div className="flex gap-4 max-w-[85%] ml-auto justify-end">
              <div className="bg-gradient-to-br from-teal-500 to-indigo-500 text-white p-4 rounded-3xl rounded-tr-sm shadow-md text-sm leading-relaxed">
                <p>Yarın sabah 09:30 uçağıyla geliyoruz. 2 kişiyiz, uçuş kodumuz TK2420. Bizi Alanya'daki bir otele götürür müsünüz?</p>
              </div>
              <div className="w-10 h-10 rounded-full bg-slate-200 flex items-center justify-center shrink-0 overflow-hidden">
                <img src={`https://ui-avatars.com/api/?name=User&background=cbd5e1&color=475569`} alt="User" className="w-full h-full object-cover" />
              </div>
            </div>

            {/* AI Message */}
            <div className="flex gap-4 max-w-[85%]">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-teal-100 to-indigo-100 flex items-center justify-center shrink-0 border border-indigo-50">
                <Sparkles className="w-5 h-5 text-indigo-600" />
              </div>
              <div className="bg-white p-4 rounded-3xl rounded-tl-sm shadow-sm border border-slate-100 text-slate-700 text-sm leading-relaxed">
                <p>Harika! TK2420 sefer sayılı uçuşunuzu buldum. İniş saatiniz 10:45 olarak görünüyor.</p>
                <p className="mt-2">Rezervasyon özetinizi aşağıda oluşturdum. Onaylıyor musunuz?</p>
              </div>
            </div>

            {/* Summary Card */}
            {showSummary && (
              <div className="flex gap-4 max-w-[90%] md:max-w-[75%] ml-14">
                <div className="bg-white rounded-3xl overflow-hidden border-2 border-teal-400 shadow-xl shadow-teal-500/10 w-full relative">
                  {/* Card Header */}
                  <div className="bg-gradient-to-r from-teal-400 to-indigo-500 p-4 text-white flex justify-between items-center relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full blur-2xl -mr-10 -mt-10"></div>
                    <div className="relative z-10 flex items-center gap-2">
                      <CheckCircle2 className="w-5 h-5" />
                      <span className="font-bold text-sm tracking-wide">REZERVASYON OLUŞTURULDU</span>
                    </div>
                    <div className="relative z-10 bg-white/20 backdrop-blur-md px-3 py-1 rounded-full text-xs font-bold font-mono tracking-wider">
                      VT-9X2P
                    </div>
                  </div>
                  
                  {/* Card Body */}
                  <div className="p-5 space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <span className="text-[10px] uppercase font-bold text-slate-400 flex items-center gap-1"><Ticket className="w-3 h-3" /> YOLCU</span>
                        <p className="text-sm font-bold text-slate-800">Ahmet Yılmaz +1</p>
                      </div>
                      <div className="space-y-1">
                        <span className="text-[10px] uppercase font-bold text-slate-400 flex items-center gap-1"><Plane className="w-3 h-3" /> UÇUŞ NO</span>
                        <p className="text-sm font-bold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded inline-block">TK 2420</p>
                      </div>
                    </div>

                    <div className="h-px w-full bg-slate-100"></div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <span className="text-[10px] uppercase font-bold text-slate-400 flex items-center gap-1"><Calendar className="w-3 h-3" /> TARİH</span>
                        <p className="text-sm font-bold text-slate-800">24 Ekim 2023</p>
                      </div>
                      <div className="space-y-1">
                        <span className="text-[10px] uppercase font-bold text-slate-400 flex items-center gap-1"><Clock className="w-3 h-3" /> İNİŞ SAATİ</span>
                        <p className="text-sm font-bold text-slate-800">10:45</p>
                      </div>
                    </div>

                    <div className="bg-slate-50 p-3 rounded-2xl border border-slate-100 space-y-3">
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5"><MapPin className="w-4 h-4 text-teal-500" /></div>
                        <div>
                          <p className="text-xs text-slate-500 font-medium">Nereden</p>
                          <p className="text-sm font-bold text-slate-800">Antalya Havalimanı (AYT)</p>
                        </div>
                      </div>
                      <div className="ml-1.5 w-0.5 h-3 bg-slate-200"></div>
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5"><MapPin className="w-4 h-4 text-indigo-500" /></div>
                        <div>
                          <p className="text-xs text-slate-500 font-medium">Nereye</p>
                          <p className="text-sm font-bold text-slate-800">Alanya Merkez Otel</p>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-2">
                      <div className="space-y-0.5">
                        <span className="text-[10px] uppercase font-bold text-slate-400">TOPLAM TUTAR</span>
                        <p className="text-xl font-black text-slate-800 flex items-center gap-1">
                          € 65.00 <span className="text-xs font-medium text-slate-400 line-through">€80.00</span>
                        </p>
                      </div>
                      <button className="bg-slate-900 hover:bg-slate-800 text-white px-5 py-2.5 rounded-xl text-sm font-bold transition-colors flex items-center gap-2">
                        <CreditCard className="w-4 h-4" />
                        Öde ve Onayla
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
            
            {/* Scroll Anchor */}
            <div className="h-4"></div>
          </div>

          {/* Input Area */}
          <div className="p-4 md:p-6 bg-white border-t border-indigo-50">
            <div className="relative flex items-center">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder="Örn: Uçuş kodum TK2420, 2 kişi Alanya'ya gideceğiz..."
                className="w-full bg-slate-50 border border-slate-200 text-slate-800 text-sm rounded-full py-4 pl-6 pr-14 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent transition-all placeholder:text-slate-400 shadow-sm"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && inputValue.trim()) {
                    setInputValue('');
                  }
                }}
              />
              <button 
                className="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 bg-gradient-to-tr from-teal-400 to-indigo-500 hover:opacity-90 rounded-full flex items-center justify-center text-white transition-all shadow-md transform hover:scale-105 active:scale-95"
                onClick={() => {
                  if (inputValue.trim()) setInputValue('');
                }}
              >
                <Send className="w-4 h-4 ml-0.5" />
              </button>
            </div>
            <div className="flex justify-center mt-3 gap-4 text-[10px] font-medium text-slate-400">
              <span>Powered by OpenAI</span>
              <span>•</span>
              <span>7/24 Kesintisiz Hizmet</span>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
