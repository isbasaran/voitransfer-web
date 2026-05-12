import React, { useState } from 'react';
import './_glass.css';
import { Plane, Send, User, MapPin, Calendar, Clock, CreditCard, Hash, CheckCircle2, ChevronRight, MessageSquare, Plus, Search, Edit2, XCircle } from 'lucide-react';

interface Message {
  id: string;
  sender: 'ai' | 'user';
  text: string;
  time: string;
}

interface Reservation {
  voucher: string;
  passenger: string;
  flight: string;
  date: string;
  time: string;
  from: string;
  to: string;
  price: string;
  status: 'confirmed' | 'pending' | 'cancelled';
}

export function GlassAI() {
  const [activeTab, setActiveTab] = useState<'new' | 'check' | 'edit' | 'cancel'>('new');
  const [inputValue, setInputValue] = useState('');

  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      sender: 'ai',
      text: 'Merhaba! VoiTransfer AI asistanına hoş geldiniz. Size nasıl yardımcı olabilirim? Yeni bir transfer rezervasyonu yapmak, mevcut rezervasyonunuzu sorgulamak veya iptal etmek isterseniz bana yazabilirsiniz.',
      time: '10:42',
    },
    {
      id: '2',
      sender: 'user',
      text: 'Yarın sabah İstanbul Havalimanı\'ndan Kadıköy\'e gitmek istiyorum.',
      time: '10:43',
    },
    {
      id: '3',
      sender: 'ai',
      text: 'Harika, İstanbul Havalimanı (IST) - Kadıköy transferiniz için yardımcı olacağım. Uçuş numaranızı ve saatinizi öğrenebilir miyim?',
      time: '10:43',
    },
    {
      id: '4',
      sender: 'user',
      text: 'TK2123, iniş saati 09:15',
      time: '10:45',
    },
    {
      id: '5',
      sender: 'ai',
      text: 'Teşekkürler. İşleminizi tamamlamak için yolcu sayısını ve isim soyisim bilgisini alabilir miyim?',
      time: '10:45',
    },
    {
      id: '6',
      sender: 'user',
      text: '2 kişi, Ahmet Yılmaz',
      time: '10:46',
    },
    {
      id: '7',
      sender: 'ai',
      text: 'Bilgilerinizi aldım. VIP Vito aracımızla IST - Kadıköy transferiniz 1200 TL tutmaktadır. Onaylıyor musunuz?',
      time: '10:46',
    },
  ]);

  const [showSummary, setShowSummary] = useState(true);

  const mockReservation: Reservation = {
    voucher: 'VT-8492-XZ',
    passenger: 'Ahmet Yılmaz (+1)',
    flight: 'TK2123',
    date: '24 Ekim 2023',
    time: '09:15',
    from: 'İstanbul Havalimanı (IST)',
    to: 'Kadıköy, İstanbul',
    price: '1.200 ₺',
    status: 'confirmed'
  };

  const handleSend = () => {
    if (!inputValue.trim()) return;
    
    const newMessage: Message = {
      id: Date.now().toString(),
      sender: 'user',
      text: inputValue,
      time: new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })
    };
    
    setMessages([...messages, newMessage]);
    setInputValue('');
  };

  const tabs = [
    { id: 'new', label: 'YENİ REZERVASYON', icon: <Plus size={16} /> },
    { id: 'check', label: 'SORGULA', icon: <Search size={16} /> },
    { id: 'edit', label: 'DÜZENLE', icon: <Edit2 size={16} /> },
    { id: 'cancel', label: 'İPTAL', icon: <XCircle size={16} /> },
  ] as const;

  return (
    <div className="glass-container flex flex-col items-center p-4 md:p-8">
      {/* Header */}
      <header className="w-full max-w-5xl z-10 mb-8 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center shadow-lg shadow-violet-500/30">
            <Plane className="text-white" size={24} />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-white/70">
              VoiTransfer <span className="font-light text-violet-300">AI</span>
            </h1>
            <p className="text-xs text-white/50 font-medium tracking-wider uppercase">Akıllı Asistan</p>
          </div>
        </div>
        <div className="hidden md:flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)] animate-pulse"></div>
          <span className="text-sm font-medium text-white/70">Sistem Aktif</span>
        </div>
      </header>

      {/* Main Content */}
      <main className="w-full max-w-5xl z-10 flex flex-col lg:flex-row gap-6 lg:gap-8 flex-1 min-h-[600px]">
        
        {/* Chat Section */}
        <section className="flex-1 flex flex-col glass-panel p-4 md:p-6 overflow-hidden">
          
          {/* Tabs */}
          <div className="flex flex-wrap gap-2 mb-6 p-1 rounded-2xl bg-black/20 backdrop-blur-md border border-white/5">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`glass-tab flex-1 min-w-[120px] py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 text-sm font-medium
                  ${activeTab === tab.id ? 'active text-white' : 'text-white/60 hover:text-white hover:bg-white/10'}`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>

          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto pr-2 space-y-6 mb-6 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
            {messages.map((msg) => (
              <div key={msg.id} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                {msg.sender === 'ai' && (
                  <div className="w-8 h-8 rounded-full bg-violet-500/20 border border-violet-500/30 flex items-center justify-center mr-3 flex-shrink-0 mt-1">
                    <Plane size={14} className="text-violet-300" />
                  </div>
                )}
                
                <div className="flex flex-col max-w-[80%]">
                  <div 
                    className={`p-4 rounded-2xl text-sm leading-relaxed
                      ${msg.sender === 'user' ? 'glass-bubble-user text-white' : 'glass-bubble-ai text-white/90'}
                    `}
                  >
                    {msg.text}
                  </div>
                  <span className={`text-[10px] text-white/40 mt-1.5 ${msg.sender === 'user' ? 'text-right mr-1' : 'ml-1'}`}>
                    {msg.time}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Input Area */}
          <div className="relative mt-auto">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="Mesajınızı buraya yazın..."
              className="glass-input w-full py-4 pl-5 pr-14 rounded-2xl text-sm transition-all"
            />
            <button
              onClick={handleSend}
              className="glass-button absolute right-2 top-2 bottom-2 aspect-square rounded-xl flex items-center justify-center"
            >
              <Send size={18} className="ml-1" />
            </button>
          </div>
        </section>

        {/* Summary Card Section */}
        {showSummary && (
          <aside className="w-full lg:w-[380px] flex flex-col gap-6">
            <div className="boarding-pass rounded-3xl p-6 md:p-8 flex flex-col">
              <div className="flex justify-between items-start mb-8">
                <div>
                  <p className="text-xs text-white/50 uppercase tracking-widest mb-1 font-semibold">Rezervasyon</p>
                  <p className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                    <CheckCircle2 className="text-emerald-400" size={20} />
                    Onay Bekliyor
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-white/50 uppercase tracking-widest mb-1 font-semibold">Voucher</p>
                  <p className="text-lg font-mono font-bold text-violet-300 bg-violet-500/10 py-1 px-2 rounded-md border border-violet-500/20">
                    {mockReservation.voucher}
                  </p>
                </div>
              </div>

              <div className="space-y-6">
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2 text-white/50 text-xs uppercase tracking-wider font-semibold">
                    <User size={14} />
                    <span>Yolcu Bilgisi</span>
                  </div>
                  <p className="text-base font-medium text-white pl-6">{mockReservation.passenger}</p>
                </div>

                <div className="flex items-center gap-4">
                  <div className="flex-1 flex flex-col gap-1">
                    <div className="flex items-center gap-2 text-white/50 text-xs uppercase tracking-wider font-semibold">
                      <Hash size={14} />
                      <span>Uçuş</span>
                    </div>
                    <p className="text-base font-medium text-white pl-6">{mockReservation.flight}</p>
                  </div>
                  <div className="w-px h-8 bg-white/10"></div>
                  <div className="flex-1 flex flex-col gap-1">
                    <div className="flex items-center gap-2 text-white/50 text-xs uppercase tracking-wider font-semibold">
                      <Calendar size={14} />
                      <span>Tarih</span>
                    </div>
                    <p className="text-base font-medium text-white pl-6">{mockReservation.date}</p>
                  </div>
                </div>

                <div className="relative py-4 my-2">
                  <div className="absolute left-2.5 top-0 bottom-0 w-px bg-gradient-to-b from-violet-400/50 via-white/10 to-blue-400/50 border-l border-dashed border-white/20"></div>
                  
                  <div className="flex flex-col gap-6 relative">
                    <div className="flex items-start gap-4">
                      <div className="w-5 h-5 rounded-full bg-[#1e1b4b] border-[4px] border-violet-400 z-10 flex-shrink-0"></div>
                      <div className="-mt-1">
                        <p className="text-xs text-white/50 uppercase tracking-wider font-semibold mb-1">Nereden</p>
                        <p className="text-base font-medium text-white">{mockReservation.from}</p>
                        <p className="text-sm text-white/60 mt-0.5">{mockReservation.time}</p>
                      </div>
                    </div>
                    
                    <div className="flex items-start gap-4">
                      <div className="w-5 h-5 rounded-full bg-[#1e1b4b] border-[4px] border-blue-400 z-10 flex-shrink-0 flex items-center justify-center">
                        <div className="w-1.5 h-1.5 bg-blue-400 rounded-full"></div>
                      </div>
                      <div className="-mt-1">
                        <p className="text-xs text-white/50 uppercase tracking-wider font-semibold mb-1">Nereye</p>
                        <p className="text-base font-medium text-white">{mockReservation.to}</p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="pt-6 border-t border-white/10 flex justify-between items-end mt-2">
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2 text-white/50 text-xs uppercase tracking-wider font-semibold">
                      <CreditCard size={14} />
                      <span>Toplam Tutar</span>
                    </div>
                    <p className="text-2xl font-bold text-white pl-6">{mockReservation.price}</p>
                  </div>
                  <button className="glass-button px-5 py-2.5 rounded-xl font-medium text-sm flex items-center gap-2 shadow-[0_0_20px_rgba(139,92,246,0.3)]">
                    Onayla
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            </div>
          </aside>
        )}
      </main>
    </div>
  );
}
