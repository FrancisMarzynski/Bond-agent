# 03-03 Podsumowanie: Projektowanie wyglądu i nawigacji

**Data ukończenia:** 2026-03-04
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 03-03 (Baza rzutowania Layoutu i wizualizacje)
**Status:** ✅ Zakończone

---

## Cel

Zbudowanie bazy wizualnej aplikacji służącej jako środowisko pracy dla redaktora systemu Bond. Postawienie komponentów szkieletu opierających się o wygenerowany stan aplikacji (z Zustand / SSE).

---

## Zmodyfikowane i Utworzone pliki

### `frontend/src/app/layout.tsx` & `page.tsx`
Fundamentalna przemiana standardowej siatki startowej z modułu Next.js do formy edytora z odciętą lewą kolumną (na Sidebara) oraz górnym headerem. 
- Usunięto standardowe style by zapobiec rozjeżdżaniu DOM za pomocą sztywnego bloku `min-w-0 overflow-hidden` dla flexboxa.
- Strona główna została ogołocona z demówek Next.js i zaprasza komponenty Pasku postępu oraz robi rezerwowe miejsce dla ChatInterface (przygotowanego pod etap wdrożeniowy Plan 04).
- Wyrenderowano globalnie komponent paska postępu (`<StageProgress />`) bezpośrednio w bloku `<main>` ponad kontenerem na `{children}`, aby na bieżąco powiadamiał użytkownika o postępie bez względu na otwieraną podstronę konwersacji.

### `frontend/src/components/Sidebar.tsx` (Nowy)
Stworzono boczny panel dla logiki obsługi.
- Lewy panel używa podpiętego `useSession()`, dzięki czemu pobiera sesje ID konwersacji (zapisane bezpiecznie w `sessionStorage`) i ładuje pod spodem odpowiednie grafiki. W innym wypadku zrzuca widok `No active session`. Zaopatrzony na górze w przycisk `<Button>` do restartu wątków wykorzystujący paczkę *lucide-react*.

### `frontend/src/components/ModeToggle.tsx` (Nowy)
Element ulokowany permanentnie w górnym Header Layoutu głównego tuż obok tutejszego tytułu ("Author mode").
- Skorzystano tu ze switcha z biblioteki `shadcn/ui`. Manipulacja dźwignią odpytuje Reactowski hook stanu asynchronicznego `const { mode, setMode } = useChatStore()` z zadania 03-02 podpinając i zmieniając go po resecie kliknięcia obustronnie: the Author Mode <-> Shadow Mode w systemie operacyjnym powiadamiając również w małej, szarej odznace na skraju `<Badge />`.

### `frontend/src/components/StageProgress.tsx` (Nowy)
Implementacja inteligentnego i reaktywnego progressbaru. Wykorzystany zostanie wyciągany krok zdarzeń (LangGraph event `stage` z API w Pythonie).
- Zastosowano trzykrokową siatkę na listach uporządkowanych HTML ze zmiennymi ikonografikami (CheckCircle2 dla zrobionych "completed" jako zielone foki oraz kręcący się Loader2 dla "running"). Jeśli stan zwróci pusty domyślny string "idle" przy resecie chatu - ukryje cały bar nie rzucając się w oczęta (tożsamo ze statycznym zachowaniem strumienia wg statusu).
- Wprowadzono odporność na błędy parsowania: po wystąpieniu craszu serwera lub przerwaniu streamowania wywołanie aktywnego kroku zostaje zachowane (nie przełącza się na generyczny "idle" lub "error"), a ikona ulega zmianie na czerwoną oznakę craszu (XCircle), by jednoznacznie zakomunikować klientowi, w którym miejscu proces napotkał awarię. Zmodyfikowano w tym celu `useStream.ts` oraz `chatStore.ts`.

---

## Weryfikacja

Wszystkie dodane pliki połączyły się perfekcyjnie w spójną całość kompilując z sukcesem architekturę komponentów. Nastąpiło walidowanie po stronie TS (`tsc`) po czym zrzut paczki kompilacyjnej za pomocą pakietu `npm run build` by potwierdzić, że wbudowane do środowiska paczki TailwindCSS ver 4 i importowanie nie zawiodły. Zero błędów i w pełni działający projekt pod portem 3000.

---

## Kryteria akceptacji (AC)

| AC | Status |
|---|---|
| Gotowy szkielet strony głównej w Next.js | ✅ Przemodelowano całe domyślne App Directory pod układ trójwarstwowy z użyciem Tailwind V4. |
| Działający przełącznik (Toggle) między trybami | ✅ Zainstalowano przełącznik na górnym barcie (ModeToggle) obsługujący pole do modyfikacji statusu Zustand w pamięci głównej. |
| Pasek postępu pokazujący, na jakim etapie jest praca | ✅ Stworzono reagujący na zmiany kroku parsera LangGraph animowany pasek Stepper po stronie Frontend na wzór "StageProgress", trzymający trzystopniową historię. |
