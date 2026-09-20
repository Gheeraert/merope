-- Mérope: Markdown "encadré" -> native TEI Commons Publishing floatingText.
--
-- Pandoc's TEI writer silently drops a fenced div (its class, attributes and
-- wrapper all vanish) and would turn any heading inside it into a section
-- that swallows the rest of the document. This filter therefore rewrites the
-- reserved Mérope div into raw TEI *before* the writer runs:
--
--   :::: {.merope-encadre}
--   ::: {.merope-encadre-titre}
--   Titre
--   :::
--
--   Paragraphes...
--   ::::
--
-- becomes
--
--   <floatingText><body><div type="section1">
--     <head>Titre</head>
--     <p>Paragraphes...</p>
--   </div></body></floatingText>
--
-- (the construction TEI Commons Publishing documents for an encadré).
-- Class names must stay in sync with bloggen/markdown/box_syntax.py.

local BOX_CLASS = 'merope-encadre'
local TITLE_CLASS = 'merope-encadre-titre'

local function tei_inline(inlines)
  -- Render inlines with Pandoc's own TEI writer, then drop the <p> wrapper
  -- it adds around a Plain: <head> holds inline content only.
  local out = pandoc.write(pandoc.Pandoc({ pandoc.Plain(inlines) }), 'tei')
  out = out:gsub('^%s*<p>', ''):gsub('</p>%s*$', '')
  return out
end

local function refuse(message)
  error('Encadré Mérope non pris en charge : ' .. message, 0)
end

function Div(div)
  if not div.classes:includes(BOX_CLASS) then
    return nil
  end

  local blocks = {}
  for _, block in ipairs(div.content) do
    blocks[#blocks + 1] = block
  end

  local title = nil
  if #blocks > 0 and blocks[1].t == 'Div' and blocks[1].classes:includes(TITLE_CLASS) then
    local title_div = table.remove(blocks, 1)
    local first = title_div.content[1]
    if #title_div.content ~= 1 or not (first.t == 'Para' or first.t == 'Plain') then
      refuse('le titre doit tenir en un seul paragraphe.')
    end
    title = first.content
  end

  for _, block in ipairs(blocks) do
    if block.t == 'Header' then
      refuse('un titre Markdown (#) n\'est pas admis dans un encadré.')
    elseif block.t == 'Div' and (block.classes:includes(BOX_CLASS)
        or block.classes:includes(TITLE_CLASS)) then
      refuse('encadré imbriqué ou titre mal placé.')
    end
  end

  if title == nil and #blocks == 0 then
    return {}
  end

  local out = { pandoc.RawBlock('tei', '<floatingText><body><div type="section1">') }
  if title ~= nil then
    out[#out + 1] = pandoc.RawBlock('tei', '<head>' .. tei_inline(title) .. '</head>')
  end
  for _, block in ipairs(blocks) do
    out[#out + 1] = block
  end
  out[#out + 1] = pandoc.RawBlock('tei', '</div></body></floatingText>')
  return out
end
