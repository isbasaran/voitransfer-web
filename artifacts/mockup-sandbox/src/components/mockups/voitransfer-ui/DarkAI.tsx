import React, { useState, useEffect, useRef } from "react";
import { Send, Bot, User, MapPin, Calendar, Clock, CreditCard, Hash, PlaneTakeoff, Info, CheckCircle2 } from "lucide-react";
import "./_group.css";

type TabType = "new" | "check" | "edit" | "cancel";

type Message = {
  id: string;
  role: "ai" | "user";
  content: React.ReactNode;
  timestamp: string;
};

type ReservationData = {
  voucher: string;
  passenger: string;
  flight: string;
  date: string;
  time: string;
  from: string;
  to: string;
  price: string;
};

export function DarkAI() {
  const [activeTab, setActiveTab] = useState<TabType>("new");
  const [input, setInput] = useState("");
  const [showSummary, setShowSummary] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      role: "ai",
      content: "Merhaba! Ben VoiTransfer yapay zeka asistanınız. Size nasıl yardımcı olabilirim? Yeni bir transfer rezervasyonu yapmak, mevcut rezervasyonunuzu sorgulamak, düzenlemek veya iptal etmek isteyip istemediğinizi belirtebilirsiniz.",
      timestamp: "10:42",
    },
  ]);

  const mockData: ReservationData = {
    voucher: "VOI-8X9P2M",
    passenger: "Ahmet Yılmaz",
    flight: "TK2410",
    date: "24 Ekim 2024",
    time: "14:30",
    from: "Antalya Havalimanı (AYT)",
    to: "Rixos Premium Belek",
    price: "€45.00"
  };

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, showSummary]);

  const handleSend = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim()) return;

    const newUserMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input,
      timestamp: new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, newUserMsg]);
    setInput("");

    // Simulate AI response based on active tab and input length
    setTimeout(() => {
      let aiResponse = "";
      let willShowSummary = false;

      if (activeTab === "new") {
        if (messages.length < 3) {
           aiResponse = "Harika. Lütfen uçuş numaranızı, yolcu sayısını ve gideceğiniz oteli belirtebilir misiniz?";
        } else {
           aiResponse = "Tüm bilgileri aldım. Rezervasyon özetinizi aşağıda görebilirsiniz. Onaylıyor musunuz?";
           willShowSummary = true;
        }
      } else if (activeTab === "check") {
         aiResponse = "Voucher numaranızı kontrol ettim. Rezervasyonunuz aktif ve onaylanmıştır. İşte detaylar:";
         willShowSummary = true;
      } else if (activeTab === "edit") {
        aiResponse = "Tarih değişikliği talebinizi aldım. Yeni tarihe göre rezervasyonunuz güncellendi. Güncel özet aşağıdadır:";
        willShowSummary = true;
      } else {
        aiResponse = "İptal talebinizi işleme aldım. Rezervasyonunuz iptal edilmiştir. İptal edilen rezervasyonun detayları:";
        willShowSummary = true;
      }

      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: "ai",
        content: aiResponse,
        timestamp: new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })
      }]);

      if (willShowSummary) {
        setTimeout(() => setShowSummary(true), 500);
      }
    }, 1000);
  };

  const tabs = [
    { id: "new", label: "YENİ REZERVASYON" },
    { id: "check", label: "SORGULA" },
    { id: "edit", label: "DÜZENLE" },
    { id: "cancel", label: "İPTAL" },
  ];

  const handleTabChange = (tabId: TabType) => {
    setActiveTab(tabId);
    setShowSummary(false);
    let initialMsg = "";
    if (tabId === "new") initialMsg = "Yeni transfer rezervasyonunuz için havalimanı ve varış noktanızı öğrenebilir miyim?";
    else if (tabId === "check") initialMsg = "Rezervasyonunuzu sorgulamak için PNR veya Voucher numaranızı yazabilirsiniz.";
    else if (tabId === "edit") initialMsg = "Hangi rezervasyonda değişiklik yapmak istiyorsunuz? Lütfen Voucher numaranızı iletin.";
    else initialMsg = "İptal etmek istediğiniz rezervasyonun Voucher numarasını paylaşır mısınız?";

    setMessages([{
      id: Date.now().toString(),
      role: "ai",
      content: initialMsg,
      timestamp: new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })
    }]);
  };

  return (
    <div className="dark-ai-theme min-h-screen w-full flex items-center justify-center p-4 sm:p-6 lg:p-8 font-sans selection:bg-[hsl(var(--accent-base))] selection:text-white">
      
      {/* Abstract Background Elements */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-[hsl(var(--accent-base))] opacity-[0.03] blur-[120px]"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-[hsl(var(--accent-base))] opacity-[0.03] blur-[120px]"></div>
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0IiBoZWlnaHQ9IjQiPgo8cmVjdCB3aWR0aD0iNCIgaGVpZ2h0PSI0IiBmaWxsPSIjZmZmIiBmaWxsLW9wYWNpdHk9IjAuMDIiLz4KPC9zdmc+')] opacity-20 mix-blend-overlay"></div>
      </div>

      <div className="w-full max-w-5xl h-[85vh] min-h-[600px] flex flex-col relative z-10 dark-glass-panel rounded-2xl overflow-hidden shadow-2xl">
        
        {/* Header & Navigation */}
        <div className="flex flex-col border-b border-[hsl(var(--border-dim))] bg-[hsl(var(--bg-surface))] bg-opacity-50 backdrop-blur-md z-20">
          <div className="flex items-center justify-between px-6 py-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded bg-gradient-to-br from-[hsl(var(--accent-base))] to-blue-700 flex items-center justify-center shadow-[0_0_15px_rgba(0,120,255,0.4)]">
                <Bot className="w-5 h-5 text-white" />
              </div>
              <h1 className="text-xl font-bold tracking-tight text-[hsl(var(--text-main))] flex items-center gap-2">
                VoiTransfer <span className="text-[hsl(var(--text-accent))] font-mono text-sm px-2 py-0.5 rounded bg-[hsl(var(--accent-base)_/_0.1)] border border-[hsl(var(--accent-base)_/_0.2)]">AI</span>
              </h1>
            </div>
            <div className="flex items-center gap-2 text-[hsl(var(--text-muted))] text-sm">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.6)]"></span>
              Sistem Aktif
            </div>
          </div>

          <div className="flex overflow-x-auto hide-scrollbar px-6 pb-4 gap-2">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id as TabType)}
                data-state={activeTab === tab.id ? "active" : "inactive"}
                className="nav-pill px-5 py-2 rounded-full text-sm font-medium whitespace-nowrap"
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col lg:flex-row overflow-hidden relative">
          
          {/* Chat Section */}
          <div className={`flex-1 flex flex-col transition-all duration-500 ${showSummary ? 'lg:max-w-2xl border-r border-[hsl(var(--border-dim))]' : 'w-full'}`}>
            
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-6 scroll-smooth">
              {messages.map((msg, i) => (
                <div key={msg.id} className={`flex gap-4 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                  {/* Avatar */}
                  <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center mt-1 ${
                    msg.role === "ai" 
                      ? "bg-[hsl(var(--bg-surface))] border border-[hsl(var(--border-dim))]" 
                      : "bg-[hsl(var(--accent-base)_/_0.2)] border border-[hsl(var(--accent-base)_/_0.3)] text-[hsl(var(--accent-base))]"
                  }`}>
                    {msg.role === "ai" ? <Bot className="w-4 h-4 text-[hsl(var(--text-muted))]" /> : <User className="w-4 h-4" />}
                  </div>

                  {/* Message Bubble */}
                  <div className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"} max-w-[80%]`}>
                    <div className={`px-5 py-3.5 rounded-2xl text-[0.95rem] leading-relaxed ${
                      msg.role === "ai" 
                        ? "chat-bubble-ai rounded-tl-sm text-[hsl(var(--text-main))]" 
                        : "chat-bubble-user rounded-tr-sm text-[hsl(var(--text-main))]"
                    }`}>
                      {msg.content}
                    </div>
                    <span className="text-xs text-[hsl(var(--text-muted))] mt-2 font-mono opacity-50 px-1">
                      {msg.timestamp}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Input Area */}
            <div className="p-4 bg-[hsl(var(--bg-base))] border-t border-[hsl(var(--border-dim))] z-10">
              <form onSubmit={handleSend} className="relative flex items-center">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Mesajınızı yazın..."
                  className="w-full bg-[hsl(var(--bg-surface))] border border-[hsl(var(--border-dim))] rounded-xl pl-5 pr-14 py-4 text-[hsl(var(--text-main))] placeholder:text-[hsl(var(--text-muted))] outline-none transition-all glow-focus"
                />
                <button
                  type="submit"
                  disabled={!input.trim()}
                  className="absolute right-2 p-2.5 rounded-lg bg-[hsl(var(--accent-base))] text-white hover:bg-[hsl(var(--accent-hover))] disabled:opacity-50 disabled:hover:bg-[hsl(var(--accent-base))] transition-colors"
                >
                  <Send className="w-5 h-5" />
                </button>
              </form>
              <div className="text-center mt-3 text-xs text-[hsl(var(--text-muted))] opacity-60 flex items-center justify-center gap-1.5">
                <Info className="w-3 h-3" />
                VoiTransfer AI hata yapabilir. Lütfen önemli bilgileri kontrol edin.
              </div>
            </div>
          </div>

          {/* Summary Card Panel */}
          {showSummary && (
            <div className="w-full lg:w-[400px] flex-shrink-0 bg-[hsl(var(--bg-surface))] bg-opacity-30 border-t lg:border-t-0 lg:border-l border-[hsl(var(--border-dim))] overflow-y-auto animate-in slide-in-from-right-8 fade-in duration-500">
              <div className="p-6">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-lg font-semibold text-[hsl(var(--text-main))] flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 text-green-500" />
                    Rezervasyon Özeti
                  </h3>
                  <div className="px-3 py-1 rounded-full bg-[hsl(var(--accent-base)_/_0.1)] border border-[hsl(var(--accent-base)_/_0.2)] text-[hsl(var(--accent-base))] text-xs font-mono font-medium">
                    {mockData.voucher}
                  </div>
                </div>

                <div className="space-y-4">
                  <SummaryItem icon={<User />} label="Yolcu" value={mockData.passenger} />
                  <div className="grid grid-cols-2 gap-4">
                    <SummaryItem icon={<Calendar />} label="Tarih" value={mockData.date} />
                    <SummaryItem icon={<Clock />} label="Saat" value={mockData.time} />
                  </div>
                  <SummaryItem icon={<PlaneTakeoff />} label="Uçuş No" value={mockData.flight} />
                  
                  <div className="relative py-4">
                    <div className="absolute left-6 top-8 bottom-8 w-px bg-[hsl(var(--border-dim))]"></div>
                    <div className="space-y-6">
                      <SummaryItem icon={<MapPin className="text-[hsl(var(--accent-base))]" />} label="Nereden" value={mockData.from} />
                      <SummaryItem icon={<MapPin />} label="Nereye" value={mockData.to} />
                    </div>
                  </div>

                  <div className="pt-4 mt-4 border-t border-[hsl(var(--border-dim))]">
                    <div className="flex items-center justify-between bg-[hsl(var(--bg-surface))] p-4 rounded-xl border border-[hsl(var(--border-dim))]">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-[hsl(var(--accent-base)_/_0.1)] rounded-lg text-[hsl(var(--accent-base))]">
                          <CreditCard className="w-5 h-5" />
                        </div>
                        <span className="text-sm font-medium text-[hsl(var(--text-muted))]">Toplam Tutar</span>
                      </div>
                      <span className="text-xl font-bold text-[hsl(var(--text-main))] font-mono">{mockData.price}</span>
                    </div>
                  </div>
                  
                  <div className="pt-4 flex gap-3">
                    <button className="flex-1 py-3 px-4 rounded-xl bg-[hsl(var(--bg-surface-hover))] border border-[hsl(var(--border-dim))] text-[hsl(var(--text-main))] text-sm font-medium hover:bg-[hsl(var(--bg-surface))] transition-colors">
                      PDF İndir
                    </button>
                    <button className="flex-1 py-3 px-4 rounded-xl bg-[hsl(var(--accent-base))] text-white text-sm font-medium hover:bg-[hsl(var(--accent-hover))] shadow-[0_0_15px_rgba(0,120,255,0.3)] transition-all">
                      Onayla
                    </button>
                  </div>

                </div>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}

function SummaryItem({ icon, label, value }: { icon: React.ReactNode, label: string, value: string }) {
  return (
    <div className="flex items-start gap-4 p-3 rounded-lg hover:bg-[hsl(var(--bg-surface))] transition-colors group">
      <div className="mt-0.5 text-[hsl(var(--text-muted))] group-hover:text-[hsl(var(--text-main))] transition-colors w-5 h-5 *:w-full *:h-full">
        {icon}
      </div>
      <div>
        <p className="text-xs text-[hsl(var(--text-muted))] mb-1">{label}</p>
        <p className="text-sm font-medium text-[hsl(var(--text-main))]">{value}</p>
      </div>
    </div>
  );
}
